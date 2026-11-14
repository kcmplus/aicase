import hashlib
import json
from datetime import timedelta
from io import BytesIO
from unittest.mock import patch, Mock

import requests
from PIL import Image
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from .ai_service import encrypt_api_key
from .models import Brand, PhoneModel, DeviceProviderConnection, Device, SupplierProduct, DeviceProduct, PrintOrder, SupplierOrder, PrintRefund
from .store_catalog import stock_template
from .supplier_orders import dispatch_order, dispatch_pending, file_url


@override_settings(SUPPLIER_ORDER_ENABLED=True, SUPPLIER_PRINT_RELEASE_ENABLED=True, SUPPLIER_ORDER_PUBLIC_URL='https://aicase.example')
class SupplierOrderTests(TestCase):
    def setUp(self):
        cache.clear()
        self.key = 'a' * 64
        self.headers = {'HTTP_X_ORDER_KEY': self.key}
        brand = Brand.objects.create(code='test', name='Test')
        model = PhoneModel.objects.create(code='phone', name='Phone', brand=brand)
        self.connection = DeviceProviderConnection.objects.create(name='Vendor', shop_id='146',
            base_url='https://shop.widermatrix.cn', api_key_ciphertext=encrypt_api_key('test-vendor-authorization'))
        self.device = Device.objects.create(connection=self.connection, vendor_device_id='401', name='Device')
        product = SupplierProduct.objects.create(connection=self.connection, goods_id='17', product_id='1', phone_model=model, active=True)
        self.stock = DeviceProduct.objects.create(device=self.device, product=product, stock=3,
            template_url='https://images.example/a.png', template_imported_url='https://images.example/a.png',
            template_image='overlay.png', template_mask='mask.png', template_width=20, template_height=40,
            observed_at=timezone.now())
        self.order = PrintOrder.objects.create(owner_hash=hashlib.sha256(self.key.encode()).hexdigest(),
            mode='airwallex_live', fulfillment_type='pickup', status='pending', amount='1.00', model_name='Phone', snapshot={
                'model': 'Phone', '_inventory_item': self.stock.pk, '_template': stock_template(self.stock)})
        self.url = f'/api/v1/store/orders/{self.order.reference}/'
        self.target = {'device_id': '401', 'shop_id': '146', 'inventory_item_id': self.stock.pk}

    def post(self, suffix, data):
        return self.client.post(self.url + suffix, data=json.dumps(data), content_type='application/json', **self.headers)

    def bind(self):
        response = self.post('device/', self.target)
        self.assertEqual(response.status_code, 200, response.content)
        return SupplierOrder.objects.get(order=self.order)

    def image(self, width=20, height=40):
        output = BytesIO()
        Image.new('RGBA', (width, height), 'red').save(output, 'PNG')
        return SimpleUploadedFile('print.png', output.getvalue(), content_type='image/png')

    def prepare(self):
        self.bind()
        response = self.client.post(self.url + 'print-files/',
            {'print_image': self.image(), 'preview_image': self.image()}, **self.headers)
        self.assertEqual(response.status_code, 200, response.content)
        return SupplierOrder.objects.get(order=self.order)

    def pay(self):
        self.order.status, self.order.paid_at = 'paid', timezone.now()
        self.order.revision += 1
        self.order.save()
        self.order.refresh_from_db()

    def provider(self, result=None, status=200):
        response = Mock(status_code=status)
        response.iter_content.return_value = [json.dumps(result or {'code': 200, 'data': {'id': 123, 'trade_no': 'TRADE123'}}).encode()]
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        return context

    def test_bind_is_explicit_idempotent_and_owner_scoped(self):
        row = self.bind()
        self.bind()
        self.assertEqual(SupplierOrder.objects.count(), 1)
        self.assertRegex(row.business_number, r'^[0-9]{19}$')
        self.assertEqual(self.client.post(self.url+'device/', self.target).status_code, 403)
        self.assertEqual(self.post('device/', {**self.target, 'device_id': '402'}).status_code, 409)
        self.assertEqual(self.post('device/', {**self.target, 'shop_id': '999'}).status_code, 409)
        self.assertNotIn('authorization', self.post('device/', self.target).content.decode())

    def test_binding_rejects_wrong_or_stale_stock_template(self):
        self.order.snapshot['_inventory_item'] = 0
        self.order.save()
        self.assertEqual(self.post('device/', self.target).status_code, 409)
        self.order.snapshot['_inventory_item'] = self.stock.pk
        self.order.save()
        self.stock.observed_at = timezone.now() - timedelta(minutes=16)
        self.stock.save()
        self.assertEqual(self.post('device/', self.target).status_code, 409)

    def test_explicit_device_template_change_preserves_frozen_color_without_restricting_stock(self):
        color = {'code': 'natural', 'resource': {'templateId': 'old-template'}}
        self.order.snapshot['phoneColor'] = color
        self.order.snapshot['_inventory_item'] = 999
        self.order.save()
        response = self.post('device/', {**self.target, 'accept_template': True})
        self.assertEqual(response.status_code, 200, response.content)
        self.order.refresh_from_db()
        self.assertEqual(self.order.snapshot['phoneColor'], color)
        self.assertEqual(self.order.snapshot['phoneTemplateId'], stock_template(self.stock)['id'])
        self.bind()
        self.assertEqual(SupplierOrder.objects.count(), 1)

    def test_first_binding_can_explicitly_accept_the_scanned_devices_template(self):
        self.order.snapshot['_inventory_item'] = 999
        self.order.snapshot['photo'] = 'kept-artwork'
        self.order.save()
        response = self.post('device/', {**self.target, 'accept_template': True})
        self.assertEqual(response.status_code, 200, response.content)
        self.order.refresh_from_db()
        self.assertEqual(self.order.snapshot['_inventory_item'], self.stock.pk)
        self.assertEqual(self.order.snapshot['photo'], 'kept-artwork')
        self.assertEqual(self.order.snapshot['phoneTemplateId'], stock_template(self.stock)['id'])

    def test_files_validate_dimensions_and_cannot_be_replaced(self):
        self.bind()
        response = self.client.post(self.url+'print-files/', {'print_image': self.image(21), 'preview_image': self.image()}, **self.headers)
        self.assertEqual(response.status_code, 400)
        row = self.prepare()
        self.assertEqual(row.state, 'prepared')
        output = BytesIO()
        Image.new('RGBA', (20, 40), 'blue').save(output, 'PNG')
        response = self.client.post(self.url+'print-files/', {'print_image': SimpleUploadedFile('x.png', output.getvalue()), 'preview_image': self.image()}, **self.headers)
        self.assertEqual(response.status_code, 409)

    @patch('management_api.supplier_orders.requests.post')
    def test_unpaid_and_test_orders_never_submit(self, remote):
        row = self.prepare()
        self.assertFalse(dispatch_order(row.pk))
        self.pay()
        self.order.mode = 'airwallex_test'
        self.order.save()
        self.assertFalse(dispatch_order(row.pk))
        remote.assert_not_called()

    @patch('management_api.supplier_orders.requests.post')
    def test_success_reuses_admin_credentials_and_never_submits_twice(self, remote):
        row = self.prepare()
        self.pay()
        remote.return_value = self.provider()
        self.assertEqual(dispatch_pending(), 1)
        self.assertEqual(dispatch_pending(), 0)
        self.assertFalse(dispatch_order(row.pk))
        remote.assert_called_once()
        call = remote.call_args
        self.assertEqual(call.args[0], 'https://shop.widermatrix.cn/mp/UserOrder/saveOrder')
        self.assertEqual(call.kwargs['headers']['authorization'], 'test-vendor-authorization')
        payload = call.kwargs['json']
        self.assertEqual(payload['business_number'], row.business_number)
        self.assertEqual(payload['goods_id'], 17)
        self.assertEqual(payload['device_id'], '401')
        self.assertNotIn('slot', payload)
        self.assertEqual(payload['product_pic_url'], payload['picture_origin_url'])
        row.refresh_from_db()
        self.assertEqual((row.state, row.trade_no, row.vendor_id), ('submitted', 'TRADE123', '123'))
        self.assertIsNone(row.print_confirmed_at)

    @patch('management_api.supplier_orders.requests.post', side_effect=requests.Timeout('sensitive body'))
    def test_timeout_is_unknown_and_never_retried(self, remote):
        row = self.prepare()
        self.pay()
        self.assertFalse(dispatch_order(row.pk))
        self.assertFalse(dispatch_order(row.pk))
        self.assertEqual(dispatch_pending(), 0)
        remote.assert_called_once()
        row.refresh_from_db()
        self.assertEqual(row.state, 'unknown')
        self.assertNotIn('sensitive', row.message)

    @patch('management_api.supplier_orders.requests.post')
    def test_verified_cloud_response_accepts_numeric_cloud_states_without_releasing_print(self, remote):
        row = self.prepare()
        self.pay()
        remote.return_value = self.provider({'code': 200, 'message': 'success', 'data': {
            'id': 123, 'trade_no': 'WMTEST123', 'business_number': row.business_number,
            'device_id': '401', 'goods_id': 17, 'pay_status': 0, 'print_status': 0, 'status': 2}})
        self.assertTrue(dispatch_order(row.pk))
        row.refresh_from_db()
        self.assertEqual(row.state, 'submitted')
        self.assertEqual(row.trade_no, 'WMTEST123')
        self.assertEqual(row.release_state, 'idle')
        self.assertIsNone(row.print_confirmed_at)

    @patch('management_api.supplier_orders.requests.post')
    def test_placeholder_error_and_mismatched_responses_are_unknown(self, remote):
        row = self.prepare()
        self.pay()
        for result in ({'code': 0, 'data': {'id': 0, 'trade_no': 'string'}},
                       {'code': 0, 'data': {'id': 123, 'trade_no': 'X'}},
                       {'code': 401, 'data': {'id': 123, 'trade_no': 'X'}},
                       {'code': 200, 'data': {'id': 123, 'trade_no': 'X', 'device_id': '402'}},
                       {'code': 200, 'data': {'id': 123, 'trade_no': 'X', 'goods_id': 999}},
                       {'code': 200, 'data': {'id': 123, 'trade_no': 'X', 'business_number': 'other'}}):
            SupplierOrder.objects.filter(pk=row.pk).update(state='prepared')
            remote.return_value = self.provider(result)
            self.assertFalse(dispatch_order(row.pk))
            self.assertEqual(SupplierOrder.objects.get(pk=row.pk).state, 'unknown')

    @patch('management_api.supplier_orders.requests.post')
    def test_refund_and_changed_snapshot_block_push(self, remote):
        row = self.prepare()
        self.pay()
        admin = get_user_model().objects.create_user('test-admin')
        refund = PrintRefund.objects.create(order=self.order, amount=1, currency='USD', reason='test', requested_by=admin)
        self.assertFalse(dispatch_order(row.pk))
        refund.status = 'failed'
        refund.save()
        self.order.snapshot['model'] = 'Changed'
        self.order.save()
        self.assertFalse(dispatch_order(row.pk))
        remote.assert_not_called()

    def test_stale_inflight_submission_becomes_unknown_not_prepared(self):
        row = self.prepare()
        SupplierOrder.objects.filter(pk=row.pk).update(state='submitting', submitted_at=timezone.now()-timedelta(minutes=3))
        self.assertEqual(dispatch_pending(), 0)
        row.refresh_from_db()
        self.assertEqual(row.state, 'unknown')

    @patch('management_api.supplier_orders.requests.post')
    def test_unavailable_cloud_release_never_claims_success_even_with_old_switch(self, remote):
        row = self.prepare()
        self.assertEqual(self.post('confirm-print/', {'confirm': True}).status_code, 409)
        self.pay()
        remote.return_value = self.provider()
        dispatch_order(row.pk)
        self.assertEqual(self.post('confirm-print/', {'confirm': 'yes'}).status_code, 400)
        for _ in range(2):
            response = self.post('confirm-print/', {'confirm': True})
            self.assertEqual(response.status_code, 503)
            self.assertIn('not enabled', response.json()['detail'])
        row.refresh_from_db()
        self.assertIsNone(row.print_confirmed_at)
        self.assertEqual(row.release_state, 'idle')
        self.assertEqual(self.order.status, 'paid')
        config = self.client.get('/api/v1/store/fulfillment-config/', **self.headers).json()
        self.assertFalse(config['release_enabled'])
        from .supplier_orders import public_state
        self.assertFalse(public_state(self.order)['can_confirm_print'])
        remote.assert_called_once()  # Only saveOrder; no invented free HTTP write.

    def test_private_files_require_signed_matching_token_and_submission_state(self):
        row = self.prepare()
        token = signing.dumps({'reference':str(row.order.reference),'sha':row.image_sha256,'kind':'print'}, salt='supplier-print-file-v1')
        url = '/api/v1/supplier-order-files/'+token+'/'
        self.assertEqual(self.client.get(url).status_code, 404)
        row.state = 'submitting'
        row.save()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(self.client.get(url.replace('supplier-order-files/', 'supplier-order-files/x')).status_code, 404)
        row.image_sha256 = 'b' * 64
        row.save()
        self.assertEqual(self.client.get(url).status_code, 404)

    @override_settings(SUPPLIER_ORDER_ENABLED=False)
    @patch('management_api.supplier_orders.requests.post')
    def test_real_push_is_disabled_until_explicitly_configured(self, remote):
        row = self.prepare()
        self.pay()
        self.assertFalse(dispatch_order(row.pk))
        remote.assert_not_called()

    @patch('management_api.supplier_orders.requests.post')
    def test_overlapping_worker_cannot_send_an_inflight_order(self, remote):
        row = self.prepare()
        self.pay()
        def overlap(*args, **kwargs):
            self.assertFalse(dispatch_order(row.pk))
            return self.provider()
        remote.side_effect = overlap
        self.assertTrue(dispatch_order(row.pk))
        remote.assert_called_once()

    @patch('management_api.supplier_orders.requests.post')
    def test_refund_after_push_blocks_customer_confirmation(self, remote):
        row = self.prepare()
        self.pay()
        remote.return_value = self.provider()
        self.assertTrue(dispatch_order(row.pk))
        admin = get_user_model().objects.create_user('refund-admin')
        PrintRefund.objects.create(order=self.order, amount=1, currency='USD', reason='test', requested_by=admin)
        self.assertEqual(self.post('confirm-print/', {'confirm': True}).status_code, 409)
        row.refresh_from_db()
        self.assertIsNone(row.print_confirmed_at)

    @patch('management_api.supplier_orders.requests.post')
    def test_stock_is_rechecked_at_dispatch_without_switching_devices(self, remote):
        row = self.prepare()
        self.pay()
        self.stock.stock = 0
        self.stock.save()
        self.assertFalse(dispatch_order(row.pk))
        remote.assert_not_called()
        row.refresh_from_db()
        self.assertEqual(row.device_id, self.device.pk)


    def test_short_png_urls_expire_and_do_not_expose_unsigned_order_ids(self):
        import uuid
        row = self.prepare()
        url = file_url(row, 'print', '')
        self.assertTrue(url.endswith('/print.png'))
        self.assertLess(len('https://aicase.example'+url), 150)
        self.assertNotIn(str(self.order.reference),url)
        self.assertEqual(self.client.get(url).status_code,404)
        row.state, row.submitted_at = 'submitting', timezone.now()
        row.save()
        response=self.client.get(url)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.content,bytes(row.print_image))
        self.assertIn('no-store',response['Cache-Control'])
        self.assertEqual(self.client.get(url.replace('print.png','unknown.png')).status_code,404)
        row.submitted_at=timezone.now()-timedelta(hours=73)
        row.save()
        self.assertEqual(self.client.get(url).status_code,404)
        row.submitted_at=timezone.now(); row.file_token=uuid.uuid4(); row.save()
        self.assertEqual(self.client.get(url).status_code,404)
        self.assertEqual(self.client.get(file_url(row,'print','')).status_code,200)

    @patch('management_api.supplier_orders.requests.post')
    def test_clear_rejection_requires_explicit_retry_and_keeps_frozen_order(self,remote):
        row=self.prepare(); self.pay()
        remote.return_value=self.provider({'code':400,'message':'设备ID必须填写','data':None})
        self.assertFalse(dispatch_order(row.pk)); row.refresh_from_db()
        self.assertEqual(row.state,'rejected')
        self.assertEqual(dispatch_pending(),0)
        remote.assert_called_once()
        original=(row.business_number,row.image_sha256,row.device_id)
        body={'confirm':True,'submitted_at':row.submitted_at.isoformat()}
        self.assertEqual(self.post('retry-dispatch/',body).status_code,200)
        self.assertEqual(self.post('retry-dispatch/',body).status_code,200)
        remote.return_value=self.provider()
        self.assertEqual(dispatch_pending(),1)
        row.refresh_from_db()
        self.assertEqual((row.business_number,row.image_sha256,row.device_id),original)
        self.assertEqual(self.post('retry-dispatch/',body).status_code,409)
        self.assertEqual(dispatch_pending(),0)
        self.assertEqual(remote.call_count,2)

    @patch('management_api.supplier_orders.requests.post')
    def test_system_exception_remains_unknown_and_cannot_be_replayed(self,remote):
        row=self.prepare(); self.pay()
        remote.return_value=self.provider({'code':400,'message':'系统异常','data':None})
        self.assertFalse(dispatch_order(row.pk)); row.refresh_from_db()
        self.assertEqual(row.state,'unknown')
        self.assertEqual(self.post('retry-dispatch/',{'confirm':True,'submitted_at':row.submitted_at.isoformat()}).status_code,409)
        self.assertEqual(dispatch_pending(),0)
        remote.assert_called_once()

    def test_retry_rechecks_owner_refund_and_stock(self):
        row=self.prepare(); self.pay()
        row.state='rejected';row.submitted_at=timezone.now();row.save()
        body={'confirm':True,'submitted_at':row.submitted_at.isoformat()}
        self.headers={'HTTP_X_ORDER_KEY':'b'*64}
        self.assertEqual(self.post('retry-dispatch/',body).status_code,404)
        self.headers={'HTTP_X_ORDER_KEY':self.key}
        self.stock.stock=0;self.stock.save()
        self.assertEqual(self.post('retry-dispatch/',body).status_code,409)
        self.stock.stock=3;self.stock.save()
        self.order.status='cancelled';self.order.save()
        self.assertEqual(self.post('retry-dispatch/',body).status_code,409)
        row.refresh_from_db();self.assertEqual(row.state,'rejected')
        self.order.status='paid';self.order.save()
        admin=get_user_model().objects.create_user(username='retry-admin')
        PrintRefund.objects.create(order=self.order, amount=1, currency='USD', reason='test', requested_by=admin)
        self.assertEqual(self.post('retry-dispatch/',body).status_code,409)
