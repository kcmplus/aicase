import uuid
from unittest.mock import patch

from django.test import TestCase

from . import test_orders as order_tests
from . import test_supplier_orders as supplier_tests
from .models import PrintOrder, SupplierOrder
from .supplier_orders import dispatch_order, dispatch_pending


class DeliveryCheckoutTests(TestCase):
    setUpTestData = order_tests.StoreOrderTests.setUpTestData
    setUp = order_tests.StoreOrderTests.setUp
    create = order_tests.StoreOrderTests.create
    endpoint = order_tests.StoreOrderTests.endpoint

    def test_explicit_pickup_is_frozen_in_detail_and_list(self):
        self.payload['fulfillment_type'] = 'pickup'
        order = self.create()
        self.assertEqual(order['fulfillment_type'], 'pickup')
        self.assertEqual(self.client.get('/api/v1/store/orders/').data['results'][0]['fulfillment_type'], 'pickup')
        self.payload['fulfillment_type'] = 'air'
        self.assertEqual(self.client.post('/api/v1/store/orders/', self.payload, format='json').status_code, 409)
        self.assertEqual(PrintOrder.objects.count(), 1)

    @patch('management_api.orders.log')
    def test_unavailable_shipping_never_creates_a_chargeable_order(self, log):
        for delivery in ['courier', 'air', 'unsupported']:
            self.payload.update(fulfillment_type=delivery, request_key=str(uuid.uuid4()))
            response = self.client.post('/api/v1/store/orders/', self.payload, format='json')
            self.assertIn(response.status_code, [400, 409])
        self.assertFalse(PrintOrder.objects.exists())
        log.assert_not_called()

    def test_old_unclassified_order_requires_explicit_owner_confirmation(self):
        created = self.create()
        order = PrintOrder.objects.get(reference=created['reference'])
        order.fulfillment_type = 'unspecified'
        order.save()
        url = self.endpoint(created)+'fulfillment/'
        body = {'fulfillment_type': 'pickup', 'confirmed': True}
        self.client.credentials(HTTP_X_ORDER_KEY='b'*64)
        self.assertEqual(self.client.post(url, body, format='json').status_code, 404)
        self.client.credentials(HTTP_X_ORDER_KEY='a'*64)
        self.assertEqual(self.client.post(url, {**body, 'confirmed': False}, format='json').status_code, 400)
        self.assertEqual(self.client.post(url, {**body, 'fulfillment_type': 'air'}, format='json').status_code, 409)
        response = self.client.post(url, body, format='json')
        self.assertEqual(response.status_code, 200)
        revision = response.data['revision']
        self.assertEqual(response.data['fulfillment_type'], 'pickup')
        self.assertEqual(self.client.post(url, body, format='json').data['revision'], revision)


class DeviceDeliveryIsolationTests(TestCase):
    setUp = supplier_tests.SupplierOrderTests.setUp
    post = supplier_tests.SupplierOrderTests.post
    bind = supplier_tests.SupplierOrderTests.bind
    image = supplier_tests.SupplierOrderTests.image
    prepare = supplier_tests.SupplierOrderTests.prepare
    pay = supplier_tests.SupplierOrderTests.pay

    def test_delivery_and_unclassified_orders_cannot_bind_upload_or_confirm(self):
        for delivery in ['courier', 'air', 'unspecified']:
            self.order.fulfillment_type = delivery
            self.order.save()
            for suffix, body in [('device/', self.target), ('print-files/', {}), ('confirm-print/', {'confirm': True})]:
                response = self.post(suffix, body)
                # Multipart-only endpoint rejects JSON before any supplier operation.
                self.assertIn(response.status_code, [409, 415])
        self.assertFalse(SupplierOrder.objects.exists())

    @patch('management_api.supplier_orders.requests.post')
    def test_dispatch_rechecks_delivery_even_if_a_supplier_record_exists(self, remote):
        from django.test import override_settings
        row = self.prepare()
        self.pay()
        with override_settings(SUPPLIER_ORDER_ENABLED=True, SUPPLIER_ORDER_PUBLIC_URL='https://aicase.example'):
            for delivery in ['courier', 'air', 'unspecified']:
                PrintOrder.objects.filter(pk=self.order.pk).update(fulfillment_type=delivery)
                self.assertFalse(dispatch_order(row.pk))
                self.assertEqual(dispatch_pending(), 0)
        remote.assert_not_called()
        row.refresh_from_db()
        self.assertEqual(row.state, 'prepared')

    def test_existing_supplier_job_is_never_reclassified_or_reset(self):
        row = self.prepare()
        self.order.fulfillment_type = 'unspecified'
        self.order.save()
        response = self.post('fulfillment/', {'fulfillment_type': 'pickup', 'confirmed': True})
        self.assertEqual(response.status_code, 409)
        row.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(row.state, 'prepared')
        self.assertEqual(self.order.fulfillment_type, 'unspecified')

    @patch('management_api.airwallex_payments.create_intent')
    def test_direct_checkout_for_nonpickup_order_cannot_create_payment(self, remote):
        for delivery in ['courier', 'air', 'unspecified']:
            self.order.fulfillment_type = delivery
            self.order.save()
            self.assertEqual(self.post('checkout/', {}).status_code, 409)
        remote.assert_not_called()

    def test_nonpickup_upload_is_rejected_even_with_valid_png_files(self):
        row = self.prepare()
        self.order.fulfillment_type = 'courier'
        self.order.save()
        response = self.client.post(self.url+'print-files/',
            {'print_image': self.image(), 'preview_image': self.image()}, **self.headers)
        self.assertEqual(response.status_code, 409)
        row.refresh_from_db()
        self.assertEqual(row.state, 'prepared')
