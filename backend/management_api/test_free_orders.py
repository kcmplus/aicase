import uuid
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from . import test_orders as order_tests
from . import test_supplier_orders as supplier_tests
from .models import PricingPlan, PrintOrder, AirwallexConfig
from .payments import payment_config
from .refunds import eligible
from .supplier_orders import dispatch_order, dispatch_pending, public_state


class FreeOrderCheckoutTests(TestCase):
    setUpTestData = order_tests.StoreOrderTests.setUpTestData
    setUp = order_tests.StoreOrderTests.setUp

    def free_plan(self):
        PricingPlan.objects.filter(kind='print', active=True).update(price=0)
        self.payload.update(payment_provider='free', payment_mode='test', expected_amount='0.00')

    @patch('management_api.supplier_orders.requests.post')
    @patch('management_api.airwallex_payments.create_intent')
    @patch('management_api.stripe_payments.create_session')
    def test_zero_plan_creates_separate_no_charge_order_without_payment_calls(self, stripe, airwallex, supplier):
        self.free_plan()
        AirwallexConfig.objects.create(enabled=True, mode='live')
        config = self.client.get('/api/v1/store/payment-config/').json()
        self.assertEqual(config, {'provider':'free','mode':'test','available':True,'zero_price_test':True})
        response = self.client.post('/api/v1/store/orders/', self.payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        order = PrintOrder.objects.get(reference=response.data['reference'])
        self.assertEqual((order.mode, order.amount, order.status), ('free_test', Decimal('0'), 'paid'))
        self.assertIsNotNone(order.paid_at)
        self.assertFalse(eligible(order))
        self.assertFalse(order.payment_credentials)
        self.assertEqual(self.client.post('/api/v1/store/orders/', self.payload, format='json').data['reference'], response.data['reference'])
        self.client.credentials(HTTP_X_ORDER_KEY='b'*64)
        self.assertEqual(self.client.post('/api/v1/store/orders/', self.payload, format='json').status_code, 409)
        self.client.credentials(HTTP_X_ORDER_KEY='a'*64)
        self.assertEqual(self.client.post(f'/api/v1/store/orders/{order.reference}/checkout/',{},format='json').status_code,409)
        stripe.assert_not_called(); airwallex.assert_not_called(); supplier.assert_not_called()

    def test_customer_cannot_force_free_payment_on_a_positive_price(self):
        self.payload.update(payment_provider='free', payment_mode='test')
        self.assertEqual(self.client.post('/api/v1/store/orders/',self.payload,format='json').status_code,409)
        self.assertFalse(PrintOrder.objects.exists())
        self.free_plan()
        self.payload.update(payment_provider='airwallex',payment_mode='live')
        self.assertEqual(self.client.post('/api/v1/store/orders/',self.payload,format='json').status_code,409)
        self.assertFalse(PrintOrder.objects.exists())

    def test_restoring_price_keeps_old_free_order_and_requires_new_payment_review(self):
        self.free_plan()
        created = self.client.post('/api/v1/store/orders/', self.payload, format='json').data
        PricingPlan.objects.filter(kind='print', active=True).update(price='10.00')
        AirwallexConfig.objects.create(enabled=True, mode='live')
        self.assertEqual(payment_config()['provider'],'airwallex')
        self.assertEqual(self.client.post('/api/v1/store/orders/',self.payload,format='json').data['reference'],created['reference'])
        self.payload.update(request_key=str(uuid.uuid4()),expected_amount='10.00')
        self.assertEqual(self.client.post('/api/v1/store/orders/',self.payload,format='json').status_code,409)
        self.assertEqual(PrintOrder.objects.count(),1)


@override_settings(SUPPLIER_ORDER_ENABLED=True, SUPPLIER_PAYMENT_ENABLED=True, SUPPLIER_ORDER_PUBLIC_URL='https://aicase.example')
class FreeSupplierOrderTests(TestCase):
    setUp = supplier_tests.SupplierOrderTests.setUp
    post = supplier_tests.SupplierOrderTests.post
    bind = supplier_tests.SupplierOrderTests.bind
    image = supplier_tests.SupplierOrderTests.image
    prepare = supplier_tests.SupplierOrderTests.prepare
    provider = supplier_tests.SupplierOrderTests.provider

    def free_order(self):
        self.order.mode, self.order.amount = 'free_test', Decimal('0.00')
        self.order.status, self.order.paid_at = 'paid', timezone.now()
        self.order.save()

    @patch('management_api.supplier_orders.requests.post')
    def test_free_order_can_be_pushed_once_and_requires_explicit_print_confirmation(self, remote):
        self.free_order()
        row = self.prepare()
        remote.return_value = self.provider()
        self.assertEqual(dispatch_pending(),1)
        self.assertEqual(dispatch_pending(),0)
        remote.assert_called_once()
        self.assertTrue(remote.call_args.args[0].endswith('/mp/UserOrder/saveOrder'))
        row.refresh_from_db()
        self.assertEqual(row.state,'submitted')
        state = public_state(self.order)
        self.assertFalse(state['zero_release_unconfirmed'])
        self.assertTrue(state['release_available'])
        self.assertTrue(state['can_confirm_print'])
        row.refresh_from_db()
        self.assertIsNone(row.print_confirmed_at)
        self.assertEqual(row.release_state,'idle')
        remote.assert_called_once()

    @patch('management_api.supplier_orders.requests.post')
    def test_demo_and_channel_test_orders_do_not_gain_real_dispatch_from_zero_price(self, remote):
        self.free_order()
        row = self.prepare()
        for mode, amount, paid_at in [('demo',0,timezone.now()),('stripe_test',0,timezone.now()),
                                      ('airwallex_test',0,timezone.now()),('free_test',1,timezone.now()),('free_test',0,None)]:
            PrintOrder.objects.filter(pk=self.order.pk).update(mode=mode,amount=amount,paid_at=paid_at)
            self.assertFalse(dispatch_order(row.pk))
            self.assertEqual(dispatch_pending(),0)
        remote.assert_not_called()
