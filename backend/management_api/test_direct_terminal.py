from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from .models import Device, PrintRefund, SupplierOrder
from .supplier_orders import dispatch_order, public_state
from .supplier_payments import sync_order
from . import test_supplier_orders as fixtures


class DirectTerminalTests(TestCase):
    setUpBase = fixtures.SupplierOrderTests.setUp
    post = fixtures.SupplierOrderTests.post
    bind = fixtures.SupplierOrderTests.bind
    image = fixtures.SupplierOrderTests.image
    prepare = fixtures.SupplierOrderTests.prepare
    pay = fixtures.SupplierOrderTests.pay

    def setUp(self):
        self.setUpBase()
        self.settings_context = override_settings(DIRECT_DEBUG_ENABLED=True,
            DIRECT_DEBUG_DEVICE_ID=self.device.pk, DIRECT_DEBUG_TOKEN='t'*48,
            DIRECT_DEBUG_H5_ORIGIN='http://192.168.1.20:4174',
            SUPPLIER_ORDER_ENABLED=False, SUPPLIER_PAYMENT_ENABLED=False)
        self.settings_context.enable()
        self.addCleanup(self.settings_context.disable)
        self.order.mode, self.order.amount = 'free_test', 0
        self.order.save()
        self.auth = {'HTTP_AUTHORIZATION': 'Bearer ' + 't'*48}

    def poll(self, **auth):
        return self.client.post('/api/v1/debug-terminal/poll/', {}, **(auth or self.auth))

    def ready(self):
        row = self.prepare()
        self.pay()
        return row

    def test_phone_confirmation_drives_real_backend_queue_without_supplier(self):
        with patch('requests.post') as send, patch('management_api.device_provider.DeviceProvider.get') as query:
            row = self.ready()
            result = self.poll()
            self.assertEqual(result.status_code, 200, result.content)
            data = result.json()
            self.assertEqual(len(data['orders']), 1)
            self.assertEqual(data['orders'][0]['pay_status'], 'idle')
            self.assertIsNone(data['order'])
            self.assertTrue(public_state(self.order)['can_confirm_print'])
            first = self.post('confirm-print/', {'confirm': True})
            self.assertEqual(first.status_code, 200, first.content)
            row.refresh_from_db()
            confirmed = row.print_confirmed_at
            self.assertEqual(self.post('confirm-print/', {'confirm': True}).status_code, 200)
            row.refresh_from_db()
            self.assertEqual(row.print_confirmed_at, confirmed)
            self.assertEqual(self.poll().json()['order']['print_status'], 'printing')
            row.refresh_from_db()
            row.cloud_status['simulation_started_at'] = (timezone.now()-timedelta(seconds=30)).isoformat()
            row.save()
            data = self.poll().json()
            self.assertEqual(data['orders'][0]['print_status'], 'deliver_success')
            self.assertEqual(self.poll().json()['orders'], data['orders'])  # Refresh preserves server state.
            self.order.refresh_from_db()
            self.assertEqual(self.order.status, 'paid')  # Never claim real printing/collection.
            state = public_state(self.order)
            self.assertTrue(state['simulated'])
            self.assertFalse(state['cloud_status']['phase_verified'])
            send.assert_not_called()
            query.assert_not_called()

    def test_token_disabled_endpoint_preview_and_device_scope(self):
        self.ready()
        self.assertEqual(self.poll(HTTP_AUTHORIZATION='Bearer wrong').status_code, 403)
        self.assertEqual(self.client.post('/api/v1/debug-terminal/poll/').status_code, 403)
        data = self.poll().json()
        preview = data['orders'][0]['effect_image']
        self.assertEqual(self.client.get(preview).status_code, 403)
        self.assertEqual(self.client.get(preview, **self.auth)['Content-Type'], 'image/png')
        other = Device.objects.create(connection=self.connection, vendor_device_id='402', name='Other')
        with override_settings(DIRECT_DEBUG_DEVICE_ID=other.pk):
            self.assertEqual(self.poll().json()['orders'], [])
            self.assertEqual(self.client.get(preview, **self.auth).status_code, 404)
        with override_settings(DIRECT_DEBUG_ENABLED=False):
            self.assertEqual(self.poll().status_code, 404)
            self.assertEqual(self.client.get(preview, **self.auth).status_code, 404)
        self.assertEqual(self.client.post('/api/v1/terminal/orders/').status_code, 410)

    def test_paid_amount_test_modes_shipping_and_refunds_cannot_enter_simulator(self):
        row = self.ready()
        for mode, amount, fulfillment in [('airwallex_live', 1, 'pickup'), ('demo', 0, 'pickup'),
                                          ('airwallex_test', 0, 'pickup'), ('free_test', 0, 'courier')]:
            self.order.mode, self.order.amount, self.order.fulfillment_type = mode, amount, fulfillment
            self.order.save()
            self.assertFalse(dispatch_order(row.pk))
        self.order.mode, self.order.amount, self.order.fulfillment_type = 'free_test', 0, 'pickup'
        self.order.save()
        PrintRefund.objects.create(order=self.order, amount=0, currency='USD', status='requested')
        self.assertFalse(dispatch_order(row.pk))

    def test_disabled_simulation_never_falls_back_to_supplier(self):
        row = self.ready()
        with override_settings(DIRECT_DEBUG_ENABLED=False, SUPPLIER_ORDER_ENABLED=True, SUPPLIER_PAYMENT_ENABLED=True):
            with patch('requests.post') as send, patch('management_api.device_provider.DeviceProvider.get') as query:
                self.assertFalse(dispatch_order(row.pk))
                self.assertFalse(sync_order(row.pk, force=True))
                self.assertEqual(self.post('confirm-print/', {'confirm': True}).status_code, 409)
                send.assert_not_called()
                query.assert_not_called()

    def test_owner_refund_and_changed_template_are_rechecked_on_confirmation(self):
        row = self.ready()
        self.poll()
        url = self.url + 'confirm-print/'
        self.assertEqual(self.client.post(url, {'confirm': True}, HTTP_X_ORDER_KEY='b'*64).status_code, 404)
        self.assertEqual(self.post('confirm-print/', {'confirm': False}).status_code, 400)
        self.stock.stock = 0
        self.stock.save()
        self.assertEqual(self.post('confirm-print/', {'confirm': True}).status_code, 409)
        self.stock.stock = 3
        self.stock.save()
        PrintRefund.objects.create(order=self.order, amount=0, currency='USD', status='requested')
        self.assertEqual(self.post('confirm-print/', {'confirm': True}).status_code, 409)
        row.refresh_from_db()
        self.assertIsNone(row.print_confirmed_at)

    def test_existing_supplier_orders_are_not_adopted(self):
        row = self.ready()
        row.transport = 'supplier'
        row.save()
        with patch('requests.post') as send:
            self.assertEqual(self.poll().json()['orders'], [])
            self.assertFalse(dispatch_order(row.pk))
            send.assert_not_called()
