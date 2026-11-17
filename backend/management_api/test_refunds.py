import hashlib
import hmac
import json
import time
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

from cryptography.fernet import Fernet
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .models import PrintOrder, PrintRefund, AuditLog
from .refunds import RefundUnavailable, provider_call, reconcile
from .stripe_payments import encrypt_credentials

VALUES = {'client_id': 'private-client', 'api_key': 'private-key', 'webhook_secret': 'hook-secret',
          'secret_key': 'sk_test_private', 'account_id': str(uuid.uuid4())}


@override_settings(AI_CONFIG_ENCRYPTION_KEY=Fernet.generate_key().decode())
class RefundTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('refund-admin', password='test-password')
        self.staff = User.objects.create_user('refund-staff', is_staff=True)
        self.client = APIClient()
        self.client.force_login(self.admin)
        self.order = PrintOrder.objects.create(mode='airwallex_live', status='paid', amount=Decimal('10.00'),
            currency='USD', paid_at=timezone.now(), airwallex_payment_intent='int_original',
            payment_credentials=encrypt_credentials(VALUES), model_name='iPhone 17',
            snapshot={'code': 'POP-C-0123456789ABCDEF'})
        self.url = f'/api/v1/admin/orders/{self.order.pk}/refund/'
        self.payload = {'revision': 1, 'confirmed': True, 'reason': '顾客申请退货'}

    def result(self, status='RECEIVED', **updates):
        refund = PrintRefund.objects.get(order=self.order)
        return {'id': 'rfd_example', 'amount': 10, 'currency': 'USD', 'payment_intent_id': 'int_original',
                'status': status, 'metadata': {'order_reference': str(self.order.reference),
                    'refund_reference': str(refund.reference)}, **updates}

    def submit(self):
        return self.client.post(self.url, self.payload, format='json')

    def remote(self, order, operation, **kwargs):
        return [] if operation == 'list' else self.result()

    @patch('management_api.refunds.provider_call')
    def test_admin_only_csrf_and_explicit_confirmation(self, call):
        self.client.logout()
        self.assertEqual(self.submit().status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.submit().status_code, 403)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        csrf = APIClient(enforce_csrf_checks=True)
        csrf.force_login(self.admin)
        self.assertEqual(csrf.post(self.url, self.payload, format='json').status_code, 403)
        self.client.force_login(self.admin)
        for data in ({'confirmed': False}, {'reason': ''}, {'reason': 'a'*129}, {'amount': '1.00'}, {'revision': 2}):
            response = self.client.post(self.url, {**self.payload, **data}, format='json')
            self.assertIn(response.status_code, (400, 409))
        call.assert_not_called()
        self.assertFalse(PrintRefund.objects.exists())

    @patch('management_api.refunds.provider_call')
    def test_unpaid_demo_and_missing_payment_are_not_refundable(self, call):
        for changes in ({'status': 'pending'}, {'status': 'cancelled'}, {'mode': 'demo'},
                        {'paid_at': None}, {'amount': 0}, {'airwallex_payment_intent': None}):
            original = {k: getattr(self.order, k) for k in changes}
            PrintOrder.objects.filter(pk=self.order.pk).update(**changes)
            self.assertEqual(self.submit().status_code, 409)
            PrintOrder.objects.filter(pk=self.order.pk).update(**original)
        call.assert_not_called()

    @patch('management_api.refunds.provider_call')
    def test_full_refund_is_immutable_idempotent_and_audited(self, call):
        call.side_effect = self.remote
        response = self.submit()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['refund']['status'], 'pending')
        refund = PrintRefund.objects.get()
        self.assertEqual(refund.amount, self.order.amount)
        self.assertEqual(refund.requested_by, self.admin)
        self.payload.update(reason='不能替换原退款原因')
        self.assertEqual(self.submit().status_code, 200)
        self.assertEqual(PrintRefund.objects.count(), 1)
        self.assertEqual(PrintRefund.objects.get().reason, '顾客申请退货')
        self.assertEqual([c.args[1] for c in call.call_args_list], ['list', 'create', 'retrieve'])
        self.assertEqual(AuditLog.objects.filter(actor=self.admin, action='refund').count(), 1)
        call.return_value = self.result('ACCEPTED')
        call.side_effect = None
        self.assertEqual(self.client.get(self.url).data['refund']['status'], 'succeeded')
        refund.refresh_from_db()
        self.assertIsNotNone(refund.completed_at)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'paid')  # fulfillment history stays intact
        call.reset_mock()
        self.assertEqual(self.submit().data['refund']['status'], 'succeeded')
        call.assert_not_called()

    @patch('management_api.refunds.provider_call')
    def test_lost_response_preserves_key_then_recovers_without_new_refund(self, call):
        call.side_effect = [[], RefundUnavailable()]
        self.assertEqual(self.submit().status_code, 503)
        refund = PrintRefund.objects.get()
        self.assertEqual(refund.status, 'requested')
        call.side_effect = [[self.result()], self.result('SETTLED')]
        response = self.submit()
        self.assertEqual(response.data['refund']['status'], 'succeeded')
        self.assertEqual(PrintRefund.objects.get().reference, refund.reference)
        self.assertEqual([c.args[1] for c in call.call_args_list].count('create'), 1)

    @patch('management_api.refunds.provider_call')
    def test_refresh_never_creates_and_old_requests_cannot_be_resubmitted(self, call):
        PrintRefund.objects.create(order=self.order, amount=10, currency='USD', reason='test')
        call.return_value = []
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(call.call_args.args[1], 'list')
        PrintRefund.objects.update(created_at=timezone.now()-timedelta(days=2))
        self.assertEqual(self.submit().status_code, 409)
        self.assertTrue(all(c.args[1] == 'list' for c in call.call_args_list))

    @patch('management_api.refunds.provider_call')
    def test_external_refund_blocks_duplicate_full_refund(self, call):
        call.return_value = [{'id': 'rfd_external', 'status': 'ACCEPTED', 'metadata': {}}]
        self.assertEqual(self.submit().status_code, 409)
        self.assertEqual(call.call_count, 1)

    @patch('management_api.refunds.provider_call')
    def test_invalid_remote_amount_currency_and_identity_never_mark_refunded(self, call):
        PrintRefund.objects.create(order=self.order, amount=10, currency='USD', reason='test', provider_id='rfd_example')
        for change in ({'amount': 1}, {'currency': 'EUR'}, {'payment_intent_id': 'int_other'},
                       {'metadata': {}}, {'id': 'rfd_other'}, {'status': 'made-up'}):
            call.return_value = {**self.result('ACCEPTED'), **change}
            self.assertEqual(self.client.get(self.url).status_code, 503)
            self.assertEqual(PrintRefund.objects.get().status, 'requested')

    @patch('management_api.refunds.provider_call')
    def test_signed_webhook_retrieves_current_result_and_rejects_forgery(self, call):
        refund = PrintRefund.objects.create(order=self.order, amount=10, currency='USD', reason='test')
        body = json.dumps({'id': 'evt_refund', 'name': 'refund.accepted', 'data': {'object': self.result('ACCEPTED')}})
        stamp = str(int(time.time()*1000))
        url = '/api/v1/payments/airwallex/webhook/'
        self.assertEqual(self.client.post(url, body, content_type='application/json', HTTP_X_TIMESTAMP=stamp, HTTP_X_SIGNATURE='0'*64).status_code, 400)
        call.assert_not_called()
        signature = hmac.new(VALUES['webhook_secret'].encode(), (stamp+body).encode(), hashlib.sha256).hexdigest()
        call.return_value = self.result('RECEIVED')
        self.assertEqual(self.client.post(url, body, content_type='application/json', HTTP_X_TIMESTAMP=stamp, HTTP_X_SIGNATURE=signature).status_code, 200)
        refund.refresh_from_db()
        self.assertEqual(refund.status, 'pending')
        call.return_value = self.result('SETTLED')
        for _ in range(2):
            self.assertEqual(self.client.post(url, body, content_type='application/json', HTTP_X_TIMESTAMP=stamp, HTTP_X_SIGNATURE=signature).status_code, 200)
        self.assertEqual(AuditLog.objects.filter(summary__contains='succeeded').count(), 1)

    @patch('management_api.airwallex_payments.api_request')
    def test_airwallex_request_uses_original_account_amount_and_request_id(self, call):
        refund = PrintRefund.objects.create(order=self.order, amount=10, currency='USD', reason='test')
        intent = {'id': 'int_original', 'merchant_order_id': str(self.order.reference), 'metadata': {'order_reference': str(self.order.reference)},
                  'amount': 10, 'captured_amount': 10, 'currency': 'USD', 'status': 'SUCCEEDED'}
        call.side_effect = [intent, self.result()]
        provider_call(self.order, 'create', refund=refund)
        self.assertEqual(call.call_args.args[:3], (self.order, 'POST', '/api/v1/pa/refunds/create'))
        body = call.call_args.kwargs['body']
        self.assertEqual(body['request_id'], str(refund.reference))
        self.assertEqual(body['amount'], 10)
        self.assertEqual(body['payment_intent_id'], 'int_original')
        self.assertNotIn('account_id', body)

    @patch('management_api.refunds.stripe_client')
    def test_stripe_refund_contract_and_mapping(self, client):
        self.order.mode = 'stripe_test'
        self.order.stripe_payment_intent = 'pi_original'
        self.order.save()
        intent = {'id': 'pi_original', 'status': 'succeeded', 'amount_received': 1000, 'currency': 'usd', 'livemode': False}
        client.return_value.v1.payment_intents.retrieve.return_value.to_dict.return_value = intent
        client.return_value.v1.refunds.list.return_value.to_dict.return_value = {'data': [], 'has_more': False}
        client.return_value.v1.refunds.create.return_value.to_dict.side_effect = lambda: self.result('succeeded', id='re_example', amount=1000, currency='usd', payment_intent='pi_original')
        response = self.submit()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['refund']['status'], 'succeeded')
        args = client.return_value.v1.refunds.create.call_args
        self.assertEqual(args.args[0]['amount'], 1000)
        self.assertEqual(args.args[0]['payment_intent'], 'pi_original')
        self.assertEqual(args.kwargs['options']['idempotency_key'], 'case-refund-' + str(PrintRefund.objects.get().reference))

    def test_order_detail_exposes_refund_without_secrets_and_no_staff_refund_permission(self):
        PrintRefund.objects.create(order=self.order, amount=10, currency='USD', reason='private support note')
        response = self.client.get(f'/api/v1/admin/orders/{self.order.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['can_refund'])
        self.assertEqual(response.data['refund']['reason'], 'private support note')
        for value in VALUES.values():
            self.assertNotIn(value, json.dumps(response.data, default=str))
        from .orders import order_data
        public = order_data(self.order)
        self.assertNotIn('reason', public['refund'])
        self.assertNotIn('provider_id', public['refund'])

    @patch('management_api.refunds.provider_call')
    def test_stripe_refund_webhook_requires_signature_and_original_mode(self, call):
        self.order.mode = 'stripe_test'
        self.order.stripe_payment_intent = 'pi_original'
        self.order.save()
        PrintRefund.objects.create(order=self.order, amount=10, currency='USD', reason='test')
        result = self.result('succeeded', id='re_example', amount=1000, currency='usd', payment_intent='pi_original')
        event = {'id': 'evt_refund', 'object': 'event', 'type': 'refund.updated', 'livemode': False, 'data': {'object': result}}
        url = '/api/v1/payments/stripe/webhook/'
        def deliver(event, secret=VALUES['webhook_secret']):
            payload = json.dumps(event)
            stamp = str(int(time.time()))
            signature = hmac.new(secret.encode(), (stamp+'.'+payload).encode(), hashlib.sha256).hexdigest()
            return self.client.post(url, payload, content_type='application/json', HTTP_STRIPE_SIGNATURE=f't={stamp},v1={signature}')
        self.assertEqual(deliver(event, 'wrong').status_code, 400)
        self.assertEqual(deliver({**event, 'livemode': True}).status_code, 400)
        call.assert_not_called()
        call.return_value = result
        self.assertEqual(deliver(event).status_code, 200)
        self.assertEqual(PrintRefund.objects.get().status, 'succeeded')

    @patch('management_api.refunds.provider_call')
    def test_failed_refund_is_visible_without_retrying_money_movement(self, call):
        call.side_effect = lambda order, operation, **kw: [] if operation == 'list' else self.result('FAILED')
        self.assertEqual(self.submit().data['refund']['status'], 'failed')
        call.reset_mock()
        self.assertEqual(self.submit().data['refund']['status'], 'failed')
        call.assert_not_called()


from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from django.db import connection, connections
from django.test import TransactionTestCase


@skipUnless(connection.vendor == 'postgresql', 'Requires PostgreSQL row locks; exercised by deployment CI')
@override_settings(AI_CONFIG_ENCRYPTION_KEY=Fernet.generate_key().decode())
class ConcurrentRefundTests(TransactionTestCase):
    def test_two_admin_submissions_create_only_one_remote_refund(self):
        admin = User.objects.create_superuser('concurrent-refund', password='test-password')
        order = PrintOrder.objects.create(mode='airwallex_test', status='paid', paid_at=timezone.now(),
            amount=10, currency='USD', airwallex_payment_intent='int_original', model_name='iPhone 17',
            payment_credentials=encrypt_credentials(VALUES))
        gate = Barrier(2)
        def remote(order, operation, **kw):
            if operation == 'list':
                return []
            refund = PrintRefund.objects.get(order=order)
            return {'id': 'rfd_concurrent', 'status': 'RECEIVED', 'amount': 10, 'currency': 'USD',
                    'payment_intent_id': 'int_original', 'metadata': {'order_reference': str(order.reference),
                    'refund_reference': str(refund.reference)}}
        def submit():
            try:
                client = APIClient()
                client.force_authenticate(admin)
                gate.wait(timeout=10)
                return client.post(f'/api/v1/admin/orders/{order.pk}/refund/',
                    {'revision': 1, 'confirmed': True, 'reason': 'concurrent request'}, format='json').status_code
            finally:
                connections.close_all()
        with patch('management_api.refunds.provider_call', side_effect=remote) as call:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: submit(), range(2)))
            self.assertEqual(results, [200, 200])
            self.assertEqual(sum(c.args[1] == 'create' for c in call.call_args_list), 1)
        self.assertEqual(PrintRefund.objects.count(), 1)
