import copy
import uuid
from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase, override_settings
from . import test_stripe as stripe_tests, test_airwallex as awx_tests
from .models import PricingPlan, PrintOrder, PrintRefund, SupplierOrder
from .courier import frozen_courier_valid

ADDRESS = {'recipient': 'Synthetic recipient', 'phone': '+1 555 0100', 'region': 'US / NY / New York', 'street': '123 Test St', 'postal': '10001'}


@override_settings(AI_CONFIG_ENCRYPTION_KEY=stripe_tests.MASTER)
class CourierTests(TestCase):
    setUpTestData = classmethod(stripe_tests.StripeTests.setUpTestData.__func__)
    create = stripe_tests.StripeTests.create
    checkout = stripe_tests.StripeTests.checkout
    deliver = stripe_tests.StripeTests.deliver
    event = stripe_tests.StripeTests.event

    def setUp(self):
        stripe_tests.StripeTests.setUp(self)
        self.shipping, _ = PricingPlan.objects.update_or_create(kind='courier_shipping', defaults={'code': 'courier-shipping', 'name': 'Shipping', 'price': '4.00', 'currency': 'USD', 'active': True})
        self.payload.update(fulfillment_type='courier', delivery_address=copy.deepcopy(ADDRESS), expected_amount='14.00')

    def test_quote_address_frozen_retry_and_private_details(self):
        config = self.client.get('/api/v1/store/payment-config/?fulfillment_type=courier').data
        self.assertTrue(config['available'])
        self.assertEqual(config['quote']['shipping_amount'], '4.00')
        order = self.create()
        self.assertTrue(frozen_courier_valid(order))
        self.assertEqual(order.amount, Decimal('14.00'))
        self.assertEqual(order.delivery_address, ADDRESS)
        self.shipping.price = '9.00'; self.shipping.save()
        response = self.client.post('/api/v1/store/orders/', self.payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['shipping_quote']['shipping_amount'], '4.00')
        self.assertEqual(PrintOrder.objects.count(), 1)
        rows = self.client.get('/api/v1/store/orders/').data['results']
        self.assertNotIn('delivery_address', rows[0])
        self.payload['delivery_address']['street'] = 'Changed street'
        self.assertEqual(self.client.post('/api/v1/store/orders/', self.payload, format='json').status_code, 409)
        order.refresh_from_db(); self.assertEqual(order.delivery_address, ADDRESS)
        self.client.credentials(HTTP_X_ORDER_KEY='b'*64)
        self.assertEqual(self.client.get(f'/api/v1/store/orders/{order.reference}/').status_code, 404)
        self.assertEqual(self.checkout(order).status_code, 404)
        self.assertEqual(self.client.post('/api/v1/store/orders/', self.payload, format='json').status_code, 409)

    def test_invalid_address_price_method_and_unconfigured_channel(self):
        for changes in ({'delivery_address': {}}, {'delivery_address': {**ADDRESS, 'recipient': '  '}},
                        {'delivery_address': {**ADDRESS, 'extra': 'bad'}}, {'expected_amount': '10.00'},
                        {'expected_amount': '0.00'}, {'fulfillment_type': 'air'}, {'fulfillment_type': 'pickup'}):
            response = self.client.post('/api/v1/store/orders/', {**self.payload, **changes}, format='json')
            self.assertIn(response.status_code, (400, 409), response.data)
        self.config.enabled = False; self.config.save()
        config = self.client.get('/api/v1/store/payment-config/?fulfillment_type=courier').data
        self.assertFalse(config['available'])
        self.assertEqual(self.client.post('/api/v1/store/orders/', {**self.payload, 'payment_provider': 'demo', 'payment_mode': 'demo'}, format='json').status_code, 409)
        self.assertFalse(PrintOrder.objects.exists())

    def test_zero_print_price_still_charges_shipping_via_channel(self):
        PricingPlan.objects.filter(kind='print').update(price=0)
        self.assertEqual(self.client.get('/api/v1/store/payment-config/').data['provider'], 'free')
        config = self.client.get('/api/v1/store/payment-config/?fulfillment_type=courier').data
        self.assertEqual(config['provider'], 'stripe')
        self.assertEqual(config['quote']['total_amount'], '4.00')
        self.payload['expected_amount'] = '4.00'
        order = self.create()
        self.assertEqual(order.mode, 'stripe_test'); self.assertEqual(order.status, 'pending')
        self.assertEqual(order.amount, Decimal('4.00'))

    def test_zero_shipping_keeps_print_price_and_zero_total_is_separate_free_test(self):
        self.shipping.price = '0.00'; self.shipping.save()
        self.payload['expected_amount'] = '10.00'
        order = self.create()
        self.assertEqual(order.amount, Decimal('10.00')); self.assertEqual(order.mode, 'stripe_test')
        PricingPlan.objects.filter(kind='print').update(price=0)
        self.config.enabled = False; self.config.save()
        config = self.client.get('/api/v1/store/payment-config/?fulfillment_type=courier').data
        self.assertTrue(config['available']); self.assertTrue(config['zero_price_test'])
        self.assertEqual(config['provider'], 'free'); self.assertEqual(config['quote']['total_amount'], '0.00')
        self.payload.update(request_key=str(uuid.uuid4()), expected_amount='0.00', payment_provider='free', payment_mode='test')
        response = self.client.post('/api/v1/store/orders/', self.payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        free = PrintOrder.objects.get(reference=response.data['reference'])
        self.assertEqual(free.mode, 'free_test'); self.assertEqual(free.status, 'paid'); self.assertEqual(free.amount, 0)
        self.assertTrue(frozen_courier_valid(free)); self.assertIsNotNone(free.paid_at)
        self.assertEqual(self.client.post('/api/v1/store/orders/', self.payload, format='json').status_code, 200)
        self.assertEqual(PrintOrder.objects.count(), 2)
        self.assertEqual(self.checkout(free).status_code, 409)
        self.assertFalse(SupplierOrder.objects.exists())
        for suffix, payload in [('device/', {'device_id':'1','shop_id':'1'}), ('confirm-print/', {'confirm':True})]:
            self.assertEqual(self.client.post(f'/api/v1/store/orders/{free.reference}/{suffix}', payload, format='json').status_code, 409)

    def test_shipping_initializer_defaults_zero_and_preserves_manual_settings(self):
        from importlib import import_module
        from django.apps import apps
        from django.db import connection
        initializer = import_module('management_api.migrations.0036_courier_checkout').initialize_shipping
        self.shipping.delete()
        from types import SimpleNamespace
        initializer(apps, SimpleNamespace(connection=connection))
        plan = PricingPlan.objects.get(kind='courier_shipping')
        self.assertEqual(plan.price, 0)
        plan.price = '7.00'; plan.active = False; plan.save()
        from types import SimpleNamespace
        initializer(apps, SimpleNamespace(connection=connection))
        plan.refresh_from_db(); self.assertEqual(plan.price, Decimal('7.00')); self.assertFalse(plan.active)

    def test_disabled_shipping_and_stale_quote_do_not_create_order(self):
        self.shipping.price = '5.00'; self.shipping.save()
        self.assertEqual(self.client.post('/api/v1/store/orders/', self.payload, format='json').status_code, 409)
        self.shipping.active = False; self.shipping.save()
        self.assertEqual(self.client.get('/api/v1/store/payment-config/?fulfillment_type=courier').status_code, 409)
        self.payload['expected_amount'] = '15.00'
        self.assertEqual(self.client.post('/api/v1/store/orders/', self.payload, format='json').status_code, 409)
        self.assertFalse(PrintOrder.objects.exists())

    @patch('management_api.stripe_payments.create_session')
    def test_payment_retry_freezes_total_and_callback_never_dispatches(self, create_session):
        order = self.create()
        create_session.return_value = {'id': 'cs_test_example', 'url': 'https://checkout.stripe.com/c/pay/example', 'livemode': False}
        self.shipping.active = False; self.shipping.price = '99.00'; self.shipping.save()
        for _ in range(2): self.assertEqual(self.checkout(order).status_code, 200)
        self.assertEqual(create_session.call_count, 1)
        self.assertEqual(create_session.call_args.args[0].amount, Decimal('14.00'))
        order.refresh_from_db()
        # Verified callbacks reject a print-only amount and accept the frozen total.
        self.assertEqual(self.deliver(self.event(order, amount_total=1000)).status_code, 400)
        order.refresh_from_db(); self.assertEqual(order.status, 'pending')
        for _ in range(2): self.assertEqual(self.deliver(self.event(order, amount_total=1400)).status_code, 200)
        order.refresh_from_db(); self.assertEqual(order.status, 'paid'); self.assertEqual(order.revision, 2)
        self.assertFalse(SupplierOrder.objects.exists())
        self.assertEqual(self.checkout(order).status_code, 409)

    @patch('management_api.stripe_payments.create_session')
    def test_historical_tampered_cancelled_refunded_orders_cannot_pay(self, create_session):
        order = self.create(); quote = copy.deepcopy(order.shipping_quote)
        for changes in ({'shipping_quote': {}}, {'delivery_address': {}}, {'amount': '10.00'}, {'status': 'cancelled'}):
            PrintOrder.objects.filter(pk=order.pk).update(shipping_quote=quote, delivery_address=ADDRESS, amount='14.00', status='pending')
            PrintOrder.objects.filter(pk=order.pk).update(**changes)
            self.assertEqual(self.checkout(order).status_code, 409)
        PrintOrder.objects.filter(pk=order.pk).update(shipping_quote=quote, delivery_address=ADDRESS, amount='14.00', status='pending')
        PrintRefund.objects.create(order=order, amount='14.00', currency='USD', reason='test', status='pending')
        self.assertEqual(self.checkout(order).status_code, 409)
        create_session.assert_not_called()

    def test_admin_can_change_fixed_shipping_without_repricing_existing_orders(self):
        order = self.create()
        path = f'/api/v1/admin/plans/{self.shipping.pk}/'
        self.assertIn(self.client.patch(path, {'price': '6.00'}, format='json').status_code, (401, 403))
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.patch(path, {'price': '-1.00'}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(path, {'price': '6.00'}, format='json').status_code, 200)
        self.assertEqual(self.client.patch(path, {'monthly_credits': 1}, format='json').status_code, 400)
        self.client.force_authenticate(None)
        quote = self.client.get('/api/v1/store/payment-config/?fulfillment_type=courier').data['quote']
        self.assertEqual(quote['shipping_amount'], '6.00'); self.assertEqual(quote['total_amount'], '16.00')
        order.refresh_from_db(); self.assertEqual(order.amount, Decimal('14.00')); self.assertEqual(order.shipping_quote['shipping_amount'], '4.00')

    def test_admin_detail_exposes_address_readonly_but_list_excludes_it(self):
        order = self.create(); self.client.force_authenticate(self.admin)
        response = self.client.get(f'/api/v1/admin/orders/{order.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['delivery_address'], ADDRESS)
        self.client.patch(f'/api/v1/admin/orders/{order.pk}/', {'delivery_address': {**ADDRESS, 'street': 'Changed'}, 'amount': '1.00'}, format='json')
        order.refresh_from_db(); self.assertEqual(order.delivery_address, ADDRESS); self.assertEqual(order.amount, Decimal('14.00'))


@override_settings(AI_CONFIG_ENCRYPTION_KEY=awx_tests.MASTER)
class CourierAirwallexTests(TestCase):
    setUpTestData = classmethod(awx_tests.AirwallexTests.setUpTestData.__func__)
    create = awx_tests.AirwallexTests.create
    checkout = awx_tests.AirwallexTests.checkout
    deliver = awx_tests.AirwallexTests.deliver
    event = awx_tests.AirwallexTests.event

    def setUp(self):
        awx_tests.AirwallexTests.setUp(self)
        PricingPlan.objects.update_or_create(kind='courier_shipping', defaults={'code': 'courier-shipping', 'name': 'Shipping', 'price': '4.00', 'active': True})
        self.payload.update(fulfillment_type='courier', delivery_address=ADDRESS, expected_amount='14.00')

    def intent(self, order, **changes):
        return awx_tests.AirwallexTests.intent(self, order, amount=14, captured_amount=14 if changes.get('status') == 'SUCCEEDED' else 0, **changes)

    @patch('management_api.airwallex_payments.api_request')
    def test_timeout_reuses_frozen_amount_request_id_and_callback_is_idempotent(self, api):
        order = self.create()
        api.side_effect = awx_tests.PaymentUnavailable()
        self.assertEqual(self.checkout(order).status_code, 503)
        first = copy.deepcopy(api.call_args.kwargs['body'])
        self.assertEqual(first['amount'], 14)
        self.assertNotIn('delivery_address', first)
        PricingPlan.objects.filter(kind='courier_shipping').update(price='8.00')
        api.side_effect = None; api.return_value = self.intent(order)
        self.assertEqual(self.checkout(order).status_code, 200)
        self.assertEqual(first, api.call_args.kwargs['body'])
        api.return_value = self.intent(order, status='SUCCEEDED')
        for _ in range(2): self.assertEqual(self.deliver(self.event(order)).status_code, 200)
        order.refresh_from_db(); self.assertEqual(order.status, 'paid'); self.assertEqual(order.revision, 2)
        self.assertFalse(SupplierOrder.objects.exists())
