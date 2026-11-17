import copy
import hashlib
import hmac
import json
import time
import uuid
from io import StringIO
from unittest.mock import patch

import stripe
from cryptography.fernet import Fernet
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import StripeConfig, PrintOrder, AuditLog, PricingPlan
from .stripe_payments import credentials, encrypt_credentials

MASTER = Fernet.generate_key().decode()
SECRET = 'sk_test_placeholder123456'
WEBHOOK = 'whsec_testPlaceholder123456'
SETTINGS = '/api/v1/admin/stripe/'
HOOK = '/api/v1/payments/stripe/webhook/'


@override_settings(AI_CONFIG_ENCRYPTION_KEY=MASTER)
class StripeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_catalog', stdout=StringIO())
        cls.admin = User.objects.create_superuser('stripe-admin', 'admin@example.com', 'NotARealPassword123!')
        cls.staff = User.objects.create_user('stripe-staff', is_staff=True)

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.client.credentials(HTTP_X_ORDER_KEY='a'*64)
        self.config = StripeConfig.objects.create(enabled=True, storefront_url='https://shop.example.com/',
            test_credentials=encrypt_credentials({'secret_key': SECRET, 'webhook_secret': WEBHOOK}))
        self.payload = {'request_key': str(uuid.uuid4()), 'payment_provider': 'stripe', 'payment_mode': 'test',
            'accepted': True, 'expected_amount': '10.00', 'snapshot': {'version': 2, 'code': 'POP-C-0123456789ABCDEF',
            'source': 'collection', 'designId': 'bloom', 'model': 'iPhone 16 Pro', 'photo': '', 'effect': 'original',
            'intensity': 65, 'zoom': 100, 'x': 50, 'y': 50}}

    def create(self):
        response = self.client.post('/api/v1/store/orders/', self.payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return PrintOrder.objects.get()

    def checkout(self, order):
        return self.client.post(f'/api/v1/store/orders/{order.reference}/checkout/', {}, format='json')

    @patch('management_api.stripe_payments.create_session')
    def test_legacy_quantity_payment_guard_preserves_unknown_and_existing_sessions(self, create_session):
        order = self.create()
        for quantity in (3, 0, -1, True, '1', 1.0, None):
            for provider_id in ('', 'cs_test_existing'):
                with self.subTest(quantity=quantity, provider_id=bool(provider_id)):
                    order.snapshot = {**order.snapshot, 'quantity': quantity}
                    order.amount = '30.00'
                    order.stripe_session_id = provider_id
                    order.save()
                    before = PrintOrder.objects.filter(pk=order.pk).values().get()
                    response = self.checkout(order)
                    self.assertEqual(response.status_code, 409, response.data)
                    create_session.assert_not_called()
                    self.assertEqual(PrintOrder.objects.filter(pk=order.pk).values().get(), before)

    @patch('management_api.stripe_payments.create_session')
    def test_legacy_unpaid_multi_print_requires_review_before_payment(self, create_session):
        """An old unpaid multi-copy snapshot must not go straight to payment."""
        order = self.create()
        order.snapshot = {**order.snapshot, 'quantity': 3}
        order.amount = '30.00'
        order.save()
        create_session.return_value = {
            'id': 'cs_test_legacy_multi',
            'url': 'https://checkout.stripe.com/c/pay/legacy-multi',
            'livemode': False,
        }
        response = self.checkout(order)
        self.assertFalse(create_session.called,
            f'Unreviewed legacy multi-print reached payment: HTTP {response.status_code}')
        self.assertIn(response.status_code, (400, 409), response.data)

    def event(self, order, **changes):
        obj = {'id': 'cs_test_example', 'object': 'checkout.session', 'mode': 'payment', 'status': 'complete',
               'payment_status': 'paid', 'livemode': False, 'amount_total': 1000, 'currency': 'usd',
               'client_reference_id': str(order.reference), 'metadata': {'order_reference': str(order.reference)},
               'payment_intent': 'pi_example'}
        obj.update(changes)
        return {'id': 'evt_example', 'object': 'event', 'type': 'checkout.session.completed', 'livemode': False,
                'data': {'object': obj}}

    @patch('management_api.stripe_payments.create_session')
    def test_qa_missing_legacy_quantity_can_reuse_single_print_session(self, create_session):
        order = self.create()
        order.snapshot.pop('quantity', None)
        order.stripe_session_id = 'cs_test_existing'
        order.stripe_checkout_url = 'https://checkout.stripe.com/c/pay/existing'
        order.save()
        before = PrintOrder.objects.values().get(pk=order.pk)
        self.assertEqual(self.checkout(order).status_code, 200)
        create_session.assert_not_called()
        self.assertEqual(PrintOrder.objects.values().get(pk=order.pk), before)

    @patch('management_api.stripe_payments.create_session')
    def test_qa_live_multi_print_never_reuses_checkout_url(self, create_session):
        order = self.create()
        order.mode = 'stripe_live'
        order.snapshot = {**order.snapshot, 'quantity': 2}
        order.amount = '20.00'
        order.stripe_session_id = 'cs_live_existing'
        order.stripe_checkout_url = 'https://checkout.stripe.com/c/pay/existing'
        order.save()
        before = PrintOrder.objects.values().get(pk=order.pk)
        response = self.checkout(order)
        self.assertEqual(response.status_code, 409, response.data)
        self.assertNotIn('checkout_url', response.data)
        create_session.assert_not_called()
        self.assertEqual(PrintOrder.objects.values().get(pk=order.pk), before)

    def test_qa_delayed_legacy_multi_payment_preserves_frozen_snapshot(self):
        order = self.create()
        order.snapshot = {**order.snapshot, 'quantity': 3}
        order.amount = '30.00'
        order.stripe_session_id = 'cs_test_example'
        order.save()
        snapshot = copy.deepcopy(order.snapshot)
        event = self.event(order, amount_total=3000)
        for _ in range(2):
            self.assertEqual(self.deliver(event).status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, 'paid')
        self.assertEqual(order.snapshot, snapshot)
        self.assertEqual(str(order.amount), '30.00')
        self.assertEqual(order.revision, 2)
        self.assertEqual(AuditLog.objects.filter(actor_name='Stripe', action='payment').count(), 1)

    def deliver(self, event, secret=WEBHOOK, timestamp=None):
        payload = json.dumps(event)
        timestamp = timestamp or int(time.time())
        sig = hmac.new(secret.encode(), f'{timestamp}.{payload}'.encode(), hashlib.sha256).hexdigest()
        return self.client.post(HOOK, payload, content_type='application/json', HTTP_STRIPE_SIGNATURE=f't={timestamp},v1={sig}')

    def test_config_superuser_only_and_csrf_protected(self):
        self.assertEqual(self.client.get(SETTINGS).status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.patch(SETTINGS, {'revision': 0}, format='json').status_code, 403)
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.get(SETTINGS).status_code, 200)
        self.assertEqual(client.patch(SETTINGS, {'revision': 0, 'enabled': False}, format='json').status_code, 403)

    def test_config_masks_encrypts_preserves_and_clears_secrets(self):
        self.client.force_login(self.admin)
        result = self.client.get(SETTINGS)
        self.assertNotIn(SECRET, json.dumps(result.data))
        self.assertNotIn(WEBHOOK, json.dumps(result.data))
        result = self.client.patch(SETTINGS, {'revision': 0, 'test': {'secret_key': '', 'webhook_secret': ''}, 'enabled': False}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data['mode'], 'test')
        self.config.refresh_from_db()
        self.assertEqual(credentials(self.config.test_credentials)['secret_key'], SECRET)
        self.assertNotIn(SECRET, self.config.test_credentials)
        self.assertEqual(self.client.patch(SETTINGS, {'revision': 0}, format='json').status_code, 409)
        result = self.client.patch(SETTINGS, {'revision': 1, 'test': {'clear': True}}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertFalse(result.data['test']['secret_key']['configured'])
        self.assertNotIn(SECRET, str(list(AuditLog.objects.values())))

    def test_config_rejects_incomplete_activation_invalid_urls_and_mode_keys(self):
        self.client.force_login(self.admin)
        for values in ({'mode': 'live'}, {'test': {'secret_key': 'sk_live_wrong'}},
                       {'test': {'secret_key': 'pk_test_wrong'}}, {'storefront_url': 'http://example.com'},
                       {'storefront_url': 'https://example.com/#pass'}, {'storefront_url': 'https://user@example.com'},
                       {'test': {'webhook_secret': 'not-a-secret'}}, {'unknown': True}):
            result = self.client.patch(SETTINGS, {'revision': 0, **values}, format='json')
            self.assertEqual(result.status_code, 400, result.data)
        self.config.refresh_from_db()
        self.assertEqual(self.config.revision, 0)

    @override_settings(AI_CONFIG_ENCRYPTION_KEY='')
    def test_unavailable_encryption_fails_closed(self):
        self.client.force_login(self.admin)
        self.assertFalse(self.client.get(SETTINGS).data['encryption_ready'])
        self.assertEqual(self.client.post('/api/v1/store/orders/', self.payload, format='json').status_code, 503)
        self.assertFalse(PrintOrder.objects.exists())

    def test_public_config_contains_no_credentials_and_order_starts_unpaid(self):
        result = self.client.get('/api/v1/store/payment-config/')
        self.assertEqual(result.data, {'provider': 'stripe', 'mode': 'test', 'available': True})
        order = self.create()
        self.assertEqual(order.status, 'pending')
        self.assertEqual(order.mode, 'stripe_test')
        body = self.client.get(f'/api/v1/store/orders/{order.reference}/').data
        for key in ('payment_credentials', 'payment_return_url', 'stripe_checkout_url'):
            self.assertNotIn(key, body)
        self.assertNotIn(SECRET, json.dumps(body, default=str))

    def test_provider_or_mode_changes_do_not_silently_change_payment(self):
        for values in ({'payment_provider': 'demo', 'payment_mode': 'demo'}, {'payment_mode': 'live'}):
            self.assertEqual(self.client.post('/api/v1/store/orders/', {**self.payload, **values}, format='json').status_code, 409)
        self.config.enabled = False
        self.config.save()
        self.assertEqual(self.client.post('/api/v1/store/orders/', self.payload, format='json').status_code, 409)

    def test_price_minimum_and_browser_ownership(self):
        PricingPlan.objects.filter(kind='print').update(price='0.10')
        self.payload['expected_amount'] = '0.10'
        self.assertEqual(self.client.post('/api/v1/store/orders/', self.payload, format='json').status_code, 409)
        PricingPlan.objects.filter(kind='print').update(price='10')
        self.payload['expected_amount'] = '10.00'
        order = self.create()
        self.client.credentials(HTTP_X_ORDER_KEY='b'*64)
        self.assertEqual(self.checkout(order).status_code, 404)

    @patch('management_api.stripe_payments.stripe.StripeClient')
    def test_checkout_authoritative_amount_idempotency_and_no_private_design_upload(self, sdk):
        order = self.create()
        create = sdk.return_value.v1.checkout.sessions.create
        create.return_value = stripe.checkout.Session.construct_from({'id': 'cs_test_example', 'url': 'https://checkout.stripe.com/c/pay/example', 'livemode': False}, SECRET)
        result = self.checkout(order)
        self.assertEqual(result.status_code, 200, result.data)
        first = copy.deepcopy((create.call_args.args, create.call_args.kwargs))
        self.assertEqual(first[0][0]['line_items'][0]['price_data']['unit_amount'], 1000)
        self.assertEqual(first[1]['options']['idempotency_key'], 'case-checkout-' + str(order.reference))
        self.assertNotIn('snapshot', str(first))
        self.assertNotIn('owner_hash', str(first))
        self.assertEqual(self.checkout(order).data['checkout_url'], result.data['checkout_url'])
        self.assertEqual(create.call_count, 1)
        order.refresh_from_db()
        self.assertEqual(order.status, 'pending')
        repeat = self.client.post('/api/v1/store/orders/', self.payload, format='json')
        self.assertEqual(repeat.status_code, 200)
        self.assertEqual(PrintOrder.objects.count(), 1)
        changed_mode = self.client.post('/api/v1/store/orders/', {**self.payload, 'payment_mode': 'live'}, format='json')
        self.assertEqual(changed_mode.status_code, 409)

    @patch('management_api.stripe_payments.stripe.StripeClient')
    def test_network_failure_retry_uses_same_parameters_and_pending_order(self, sdk):
        order = self.create()
        create = sdk.return_value.v1.checkout.sessions.create
        create.side_effect = stripe.APIConnectionError('secret must not appear')
        result = self.checkout(order)
        self.assertEqual(result.status_code, 503)
        self.assertNotIn('secret must not appear', str(result.data))
        first = copy.deepcopy((create.call_args.args, create.call_args.kwargs))
        self.config.storefront_url = 'https://other.example.com/'
        self.config.enabled = False
        self.config.test_credentials = ''
        self.config.save()
        create.side_effect = None
        create.return_value = stripe.checkout.Session.construct_from({'id': 'cs_test_example', 'url': 'https://checkout.stripe.com/c/pay/example', 'livemode': False}, SECRET)
        self.assertEqual(self.checkout(order).status_code, 200)
        self.assertEqual(first, (create.call_args.args, create.call_args.kwargs))
        self.assertEqual(sdk.call_args.args[0], SECRET)
        self.assertEqual(PrintOrder.objects.get().status, 'pending')

    @patch('management_api.stripe_payments.create_session')
    def test_expired_checkout_does_not_create_another_session(self, create):
        from django.utils import timezone
        from datetime import timedelta
        order = self.create()
        PrintOrder.objects.filter(pk=order.pk).update(created_at=timezone.now()-timedelta(days=2))
        self.assertEqual(self.checkout(order).status_code, 409)
        create.assert_not_called()

    def test_verified_webhook_settles_once_even_after_config_rotation(self):
        order = self.create()
        self.config.test_credentials = ''
        self.config.enabled = False
        self.config.save()
        event = self.event(order)
        self.assertEqual(self.deliver(event).status_code, 200)
        self.assertEqual(self.deliver(event).status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, 'paid')
        self.assertEqual(order.revision, 2)
        self.assertEqual(order.stripe_payment_intent, 'pi_example')
        self.assertIsNotNone(order.paid_at)
        self.assertEqual(AuditLog.objects.filter(actor_name='Stripe', action='payment').count(), 1)
        self.assertEqual(self.checkout(order).status_code, 409)

    def test_invalid_signature_and_replay_are_rejected(self):
        order = self.create()
        for kwargs in ({'secret': 'wrong'}, {'timestamp': int(time.time())-600}):
            self.assertEqual(self.deliver(self.event(order), **kwargs).status_code, 400)
        self.assertEqual(self.client.post(HOOK, '{}', content_type='application/json').status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.status, 'pending')

    def test_mismatched_amount_currency_reference_mode_or_session_never_pays(self):
        order = self.create()
        order.stripe_session_id = 'cs_test_example'
        order.save()
        for changes in ({'amount_total': 1}, {'currency': 'eur'}, {'client_reference_id': str(uuid.uuid4())},
                        {'livemode': True}, {'id': 'cs_test_other'}, {'mode': 'subscription'}):
            self.assertEqual(self.deliver(self.event(order, **changes)).status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.status, 'pending')

    def test_unpaid_completion_and_out_of_order_events(self):
        order = self.create()
        event = self.event(order, payment_status='unpaid')
        self.assertEqual(self.deliver(event).status_code, 200)
        self.assertEqual(PrintOrder.objects.get().status, 'pending')
        event['type'] = 'checkout.session.expired'
        event['data']['object']['status'] = 'expired'
        self.assertEqual(self.deliver(event).status_code, 200)
        self.assertEqual(PrintOrder.objects.get().status, 'cancelled')
        # A verified successful payment takes precedence over an earlier failure.
        self.assertEqual(self.deliver(self.event(order)).status_code, 200)
        self.assertEqual(self.deliver(event).status_code, 200)
        self.assertEqual(PrintOrder.objects.get().status, 'paid')

    def test_stripe_order_cannot_enter_demo_actions_or_be_edited(self):
        order = self.create()
        url = f'/api/v1/store/orders/{order.reference}/'
        for status in ('pending', 'paid'):
            PrintOrder.objects.filter(pk=order.pk).update(status=status)
            for action in ('start', 'cancel'):
                result = self.client.post(url+'actions/', {'revision': 1, 'code': order.snapshot['code'], 'action': action, 'station_id': 'DEMO-01'}, format='json')
                self.assertEqual(result.status_code, 409)
            result = self.client.patch(url, {'revision': 1, 'accepted': True, 'snapshot': order.snapshot}, format='json')
            self.assertEqual(result.status_code, 409)
