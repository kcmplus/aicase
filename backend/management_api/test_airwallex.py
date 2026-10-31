import copy
import hashlib
import hmac
import json
import time
import uuid
from datetime import timedelta
from io import StringIO
from unittest.mock import patch, Mock

import requests
from cryptography.fernet import Fernet
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .models import AirwallexConfig, StripeConfig, PrintOrder, AuditLog, PricingPlan
from .stripe_payments import encrypt_credentials, credentials
from .airwallex_payments import api_request, PaymentUnavailable

MASTER = Fernet.generate_key().decode()
VALUES = {'client_id': 'client-private-example', 'api_key': 'api-private-example', 'webhook_secret': 'hook-private-example'}
SETTINGS = '/api/v1/admin/airwallex/'
HOOK = '/api/v1/payments/airwallex/webhook/'


@override_settings(AI_CONFIG_ENCRYPTION_KEY=MASTER)
class AirwallexTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_catalog', stdout=StringIO())
        cls.admin = User.objects.create_superuser('awx-admin', 'admin@example.com', 'NotARealPassword123!')
        cls.staff = User.objects.create_user('awx-staff', is_staff=True)

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.client.credentials(HTTP_X_ORDER_KEY='a'*64)
        self.config = AirwallexConfig.objects.create(enabled=True, storefront_url='https://shop.example.com/',
            test_credentials=encrypt_credentials(VALUES))
        self.payload = {'request_key': str(uuid.uuid4()), 'payment_provider': 'airwallex', 'payment_mode': 'test',
            'accepted': True, 'expected_amount': '10.00', 'snapshot': {'version': 2, 'code': 'POP-C-0123456789ABCDEF',
            'source': 'collection', 'designId': 'bloom', 'model': 'iPhone 16 Pro', 'photo': '', 'effect': 'original',
            'intensity': 65, 'zoom': 100, 'x': 50, 'y': 50}}

    def create(self):
        response = self.client.post('/api/v1/store/orders/', self.payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return PrintOrder.objects.get()

    def checkout(self, order):
        return self.client.post(f'/api/v1/store/orders/{order.reference}/checkout/', {}, format='json')

    def intent(self, order, **changes):
        return {'id': 'int_example', 'request_id': str(order.reference), 'merchant_order_id': str(order.reference),
                'metadata': {'order_reference': str(order.reference)}, 'currency': 'USD', 'amount': 10,
                'status': 'REQUIRES_PAYMENT_METHOD', 'client_secret': 'intent-client-secret',
                'captured_amount': 10 if changes.get('status') == 'SUCCEEDED' else 0, **changes}

    def event(self, order, **changes):
        return {'id': 'evt_example', 'name': 'payment_intent.succeeded',
                'data': {'object': self.intent(order, status='SUCCEEDED', **changes)}}

    def deliver(self, event, secret=VALUES['webhook_secret'], timestamp=None):
        payload = json.dumps(event)
        stamp = str(timestamp if timestamp is not None else int(time.time()*1000))
        signature = hmac.new(secret.encode(), (stamp+payload).encode(), hashlib.sha256).hexdigest()
        return self.client.post(HOOK, payload, content_type='application/json', HTTP_X_TIMESTAMP=stamp, HTTP_X_SIGNATURE=signature)

    def test_admin_permissions_csrf_masks_and_revision(self):
        self.assertEqual(self.client.get(SETTINGS).status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(SETTINGS).status_code, 403)
        csrf_client = APIClient(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)
        self.assertEqual(csrf_client.patch(SETTINGS, {'revision': 0}, format='json').status_code, 403)
        self.client.force_login(self.admin)
        data = self.client.get(SETTINGS).data
        for value in VALUES.values():
            self.assertNotIn(value, json.dumps(data))
        result = self.client.patch(SETTINGS, {'revision': 0, 'enabled': False, 'test': {'api_key': ''}}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        self.config.refresh_from_db()
        self.assertEqual(credentials(self.config.test_credentials), VALUES)
        self.assertEqual(self.client.patch(SETTINGS, {'revision': 0}, format='json').status_code, 409)
        result = self.client.patch(SETTINGS, {'revision': 1, 'test': {'clear': True}}, format='json')
        self.assertEqual(result.status_code, 200)
        self.assertFalse(result.data['test']['api_key']['configured'])
        self.assertNotIn(VALUES['api_key'], str(list(AuditLog.objects.values())))

    def test_activation_requires_https_and_complete_environment(self):
        self.client.force_login(self.admin)
        for fields in ({'mode': 'live'}, {'test': {'clear': True}}, {'storefront_url': 'http://localhost:4173'},
                       {'storefront_url': 'https://user@example.com'}, {'storefront_url': 'https://example.com/#payment'},
                       {'test': {'clear': True, 'api_key': 'new'}}, {'test': {'api_key': 'abc\ndef'}}, {'extra': True}):
            result = self.client.patch(SETTINGS, {'revision': 0, **fields}, format='json')
            self.assertEqual(result.status_code, 400, result.data)
        self.config.refresh_from_db()
        self.assertEqual(self.config.revision, 0)

    def test_switching_is_atomic_and_preserves_existing_orders(self):
        order = self.create()
        stripe = StripeConfig.objects.create(storefront_url='https://shop.example.com/',
            test_credentials=encrypt_credentials({'secret_key': 'sk_test_placeholder', 'webhook_secret': 'whsec_placeholder'}))
        self.client.force_login(self.admin)
        response = self.client.patch('/api/v1/admin/stripe/', {'revision': 0, 'enabled': True}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.config.refresh_from_db()
        self.assertFalse(self.config.enabled)
        self.assertEqual(self.config.revision, 1)
        self.assertEqual(self.client.get('/api/v1/store/payment-config/').data['provider'], 'stripe')
        response = self.client.patch(SETTINGS, {'revision': 1, 'enabled': True}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        stripe.refresh_from_db()
        self.assertFalse(stripe.enabled)
        order.refresh_from_db()
        self.assertEqual(order.mode, 'airwallex_test')
        self.assertEqual(credentials(order.payment_credentials), VALUES)

    @override_settings(AI_CONFIG_ENCRYPTION_KEY='')
    def test_missing_encryption_fails_closed(self):
        self.assertFalse(self.client.get('/api/v1/store/payment-config/').data['available'])
        self.assertEqual(self.client.post('/api/v1/store/orders/', self.payload, format='json').status_code, 503)
        self.assertFalse(PrintOrder.objects.exists())

    def test_order_contract_price_and_private_fields(self):
        self.assertEqual(self.client.get('/api/v1/store/payment-config/').data,
                         {'provider': 'airwallex', 'mode': 'test', 'available': True})
        for fields in ({'payment_provider': 'demo', 'payment_mode': 'demo'}, {'payment_mode': 'live'}, {'expected_amount': '1.00'}):
            self.assertEqual(self.client.post('/api/v1/store/orders/', {**self.payload, **fields}, format='json').status_code, 409)
        order = self.create()
        self.assertEqual(order.status, 'pending')
        body = self.client.get(f'/api/v1/store/orders/{order.reference}/').data
        for key in ('payment_credentials', 'payment_return_url', 'client_secret'):
            self.assertNotIn(key, body)
        self.assertEqual(self.client.post('/api/v1/store/orders/', self.payload, format='json').status_code, 200)
        self.assertEqual(self.client.post('/api/v1/store/orders/', {**self.payload, 'payment_provider': 'stripe'}, format='json').status_code, 409)
        self.client.credentials(HTTP_X_ORDER_KEY='b'*64)
        self.assertEqual(self.checkout(order).status_code, 404)

    @patch('management_api.airwallex_payments.api_request')
    def test_checkout_reuses_intent_server_amount_and_frozen_config(self, api):
        order = self.create()
        api.return_value = self.intent(order)
        first = self.checkout(order)
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(first.data['checkout']['env'], 'demo')
        self.assertEqual(first.data['checkout']['client_secret'], 'intent-client-secret')
        self.assertIn('no-store', first['Cache-Control'])
        payload = api.call_args.kwargs['body']
        self.assertEqual(payload['amount'], 10)
        self.assertEqual(payload['request_id'], str(order.reference))
        self.assertNotIn('snapshot', payload)
        self.config.enabled = False
        self.config.test_credentials = ''
        self.config.save()
        result = self.checkout(order)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(api.call_args.args[1], 'GET')
        self.assertEqual(credentials(api.call_args.args[0].payment_credentials), VALUES)
        order.refresh_from_db()
        self.assertEqual(order.status, 'pending')
        self.assertEqual(order.airwallex_payment_intent, 'int_example')

    @patch('management_api.airwallex_payments.api_request')
    def test_interrupted_creation_retry_keeps_request_id(self, api):
        order = self.create()
        api.side_effect = PaymentUnavailable()
        self.assertEqual(self.checkout(order).status_code, 503)
        first = copy.deepcopy(api.call_args.kwargs)
        api.side_effect = None
        api.return_value = self.intent(order)
        self.assertEqual(self.checkout(order).status_code, 200)
        self.assertEqual(api.call_args.kwargs, first)

    @patch('management_api.airwallex_payments.api_request')
    def test_bad_provider_response_and_expired_creation_are_rejected(self, api):
        order = self.create()
        for change in ({'amount': 1}, {'currency': 'EUR'}, {'merchant_order_id': str(uuid.uuid4())},
                       {'metadata': {}}, {'id': '../bad'}, {'client_secret': ''}):
            api.return_value = self.intent(order, **change)
            self.assertEqual(self.checkout(order).status_code, 503)
        PrintOrder.objects.filter(pk=order.pk).update(created_at=timezone.now()-timedelta(days=2))
        api.reset_mock()
        self.assertEqual(self.checkout(order).status_code, 409)
        api.assert_not_called()

    @patch('management_api.airwallex_payments.api_request')
    def test_callback_verified_and_idempotent_after_secret_rotation(self, api):
        order = self.create()
        api.return_value = self.intent(order, status='SUCCEEDED')
        self.config.test_credentials = ''
        self.config.enabled = False
        self.config.save()
        self.assertEqual(self.deliver(self.event(order)).status_code, 200)
        self.assertEqual(self.deliver(self.event(order)).status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, 'paid')
        self.assertEqual(order.revision, 2)
        self.assertIsNotNone(order.paid_at)
        self.assertEqual(order.airwallex_payment_intent, 'int_example')
        self.assertEqual(AuditLog.objects.filter(actor_name='Airwallex', action='payment').count(), 1)
        self.assertEqual(self.checkout(order).status_code, 409)

    @patch('management_api.airwallex_payments.api_request')
    def test_bad_signature_stale_future_timestamp_and_mismatches_do_not_pay(self, api):
        order = self.create()
        for kwargs in ({'secret': 'wrong'}, {'timestamp': int(time.time()*1000)-600000},
                       {'timestamp': int(time.time()*1000)+600000}, {'timestamp': int(time.time())}):
            self.assertEqual(self.deliver(self.event(order), **kwargs).status_code, 400)
        for change in ({'amount': 1}, {'currency': 'EUR'}, {'metadata': {}}, {'merchant_order_id': str(uuid.uuid4())}):
            self.assertEqual(self.deliver(self.event(order, **change)).status_code, 400)
        api.assert_not_called()
        order.airwallex_payment_intent = 'int_bound'
        order.save()
        self.assertEqual(self.deliver(self.event(order)).status_code, 400)
        self.assertEqual(self.client.post(HOOK, '[]', content_type='application/json').status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.status, 'pending')

    @patch('management_api.airwallex_payments.api_request')
    def test_callback_retrieves_original_environment_and_never_trusts_success_redirect(self, api):
        order = self.create()
        api.side_effect = PaymentUnavailable()
        self.assertEqual(self.deliver(self.event(order)).status_code, 503)
        api.side_effect = None
        api.return_value = self.intent(order, status='PENDING')
        self.assertEqual(self.deliver(self.event(order)).status_code, 200)
        self.assertEqual(self.client.get(f'/api/v1/store/orders/{order.reference}/?result=success').data['status'], 'pending')
        self.assertEqual(api.call_args.args[0].mode, 'airwallex_test')
        api.return_value = self.intent(order, status='SUCCEEDED', amount=1)
        self.assertEqual(self.deliver(self.event(order)).status_code, 400)

    @patch('management_api.airwallex_payments.api_request')
    def test_partial_or_missing_capture_never_fulfills_full_order(self, api):
        order = self.create()
        for captured in (None, 0, 5, 'NaN', 'bad'):
            api.return_value = self.intent(order, status='SUCCEEDED', captured_amount=captured)
            self.assertEqual(self.deliver(self.event(order)).status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.status, 'pending')
        self.assertFalse(AuditLog.objects.filter(actor_name='Airwallex', action='payment').exists())

    @patch('management_api.airwallex_payments.api_request')
    def test_failed_attempts_and_out_of_order_cancellations(self, api):
        order = self.create()
        event = self.event(order)
        event['name'] = 'payment_intent.payment_failed'
        self.assertEqual(self.deliver(event).status_code, 200)
        api.assert_not_called()
        api.return_value = self.intent(order, status='CANCELLED')
        event['name'] = 'payment_intent.cancelled'
        self.assertEqual(self.deliver(event).status_code, 200)
        self.assertEqual(PrintOrder.objects.get().status, 'cancelled')
        api.return_value = self.intent(order, status='SUCCEEDED')
        self.assertEqual(self.deliver(self.event(order)).status_code, 200)
        api.return_value = self.intent(order, status='CANCELLED')
        self.assertEqual(self.deliver(event).status_code, 200)
        self.assertEqual(PrintOrder.objects.get().status, 'paid')

    def test_real_orders_cannot_use_demo_actions_or_edit_design(self):
        order = self.create()
        url = f'/api/v1/store/orders/{order.reference}/'
        for status in ('pending', 'paid'):
            PrintOrder.objects.filter(pk=order.pk).update(status=status)
            self.assertEqual(self.client.patch(url, {'revision': 1, 'accepted': True, 'snapshot': order.snapshot}, format='json').status_code, 409)
            self.assertEqual(self.client.post(url+'actions/', {'revision': 1, 'code': order.snapshot['code'], 'action': 'start', 'station_id': 'DEMO-01'}, format='json').status_code, 409)

    @patch('management_api.airwallex_payments.requests.request')
    @patch('management_api.airwallex_payments.requests.post')
    def test_api_auth_token_cache_hosts_and_safe_failures(self, login, send):
        order = self.create()
        login.return_value = Mock(status_code=200, json=lambda: {'token': 'private-token', 'expires_at': (timezone.now()+timedelta(minutes=20)).isoformat()})
        send.return_value = Mock(status_code=200, json=lambda: self.intent(order))
        for _ in range(2):
            api_request(order, 'GET', '/api/v1/pa/payment_intents/int_example')
        self.assertEqual(login.call_count, 1)
        self.assertEqual(login.call_args.args[0], 'https://api.sandbox.airwallex.com/api/v1/authentication/login')
        self.assertFalse(login.call_args.kwargs['allow_redirects'])
        self.assertIn('api.sandbox.airwallex.com', send.call_args.args[1])
        order.mode = 'airwallex_live'
        api_request(order, 'GET', '/api/v1/pa/payment_intents/int_example')
        self.assertEqual(login.call_count, 2)
        self.assertEqual(login.call_args.args[0], 'https://api.airwallex.com/api/v1/authentication/login')
        send.side_effect = requests.Timeout('private-key-must-not-leak')
        with self.assertRaises(PaymentUnavailable) as error:
            api_request(order, 'GET', '/api/v1/pa/payment_intents/int_example')
        self.assertNotIn('private-key', str(error.exception))

    @patch('management_api.airwallex_payments.requests.request')
    @patch('management_api.airwallex_payments.requests.post')
    def test_duplicate_request_recovers_original_intent(self, login, send):
        order = self.create()
        login.return_value = Mock(status_code=200, json=lambda: {'token': 'private-token', 'expires_at': (timezone.now()+timedelta(minutes=20)).isoformat()})
        send.side_effect = [Mock(status_code=400, json=lambda: {'code': 'duplicate_request'}),
            Mock(status_code=200, json=lambda: {'items': [self.intent(order)]}),
            Mock(status_code=200, json=lambda: self.intent(order))]
        response = self.checkout(order)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([call.args[0] for call in send.call_args_list], ['POST', 'GET', 'GET'])
        self.assertEqual(send.call_args_list[1].kwargs['params']['merchant_order_id'], str(order.reference))
