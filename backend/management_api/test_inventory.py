import copy
import json
from datetime import timedelta
from unittest.mock import patch, MagicMock
from cryptography.fernet import Fernet
from django.contrib.auth.models import User, Permission
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from .ai_service import encrypt_api_key
from .device_provider import DeviceProvider, ProviderError
from .inventory_sync import sync_device, SyncBusy
from .models import (DeviceProviderConnection, Device, SupplierProduct, DeviceProduct,
                     DeviceLaneStock, InventorySyncRun, Brand, PhoneModel, AuditLog)


def lane(record=100, number='8', stock=8, goods=171, device=401, shop=146):
    return {'id': record, 'device_box_num': number, 'surplus_stock': stock, 'goods_id': goods,
            'product_id': 1500, 'device_id': device, 'shop_id': shop, 'product_name': 'Example phone',
            'product_brand_name': 'Example brand', 'price': '1.00', 'is_deleted': 0, 'template_url': None,
            'specs': [{'spec_name': '型号', 'spec_value': 'Example Pro'}, {'spec_name': '版本', 'spec_value': '普通款'}]}


@override_settings(AI_CONFIG_ENCRYPTION_KEY=Fernet.generate_key().decode())
class InventoryTests(TestCase):
    def setUp(self):
        self.root = User.objects.create_superuser('inventory-root', password='TestOnly!Inventory2026')
        self.reader = User.objects.create_user('inventory-reader', is_staff=True)
        self.reader.user_permissions.add(*Permission.objects.filter(codename__in=[
            'view_device', 'view_supplierproduct', 'view_deviceproduct', 'view_inventorysyncrun']))
        self.client = APIClient()
        self.client.force_authenticate(self.root)
        self.connection = DeviceProviderConnection.objects.create(name='Test connection', base_url='https://shop.widermatrix.cn',
            shop_id='146', api_key_ciphertext=encrypt_api_key('test-only-credential'), key_last_four='tial')
        self.device = Device.objects.create(connection=self.connection, vendor_device_id='401', name='Test device')
        self.rows = [lane(), lane(101, '9', 14)]
        self.provider = MagicMock()
        self.provider.lanes.side_effect = lambda _: copy.deepcopy(self.rows)
        self.provider.config.return_value = {'currency': '', 'is_lock': 0, 'print_type': '600dpi'}
        self.provider.detail.side_effect = lambda device, goods: {'goods_id': goods, 'device_id': device, 'shop_id': 146,
            'template_url': 'https://example.com/template.png'}

    def sync(self):
        with patch('management_api.inventory_sync.DeviceProvider', return_value=self.provider):
            return sync_device(self.device.id, 'test operator')

    def test_aggregate_and_idempotent_sync_preserve_local_configuration(self):
        run = self.sync()
        self.assertEqual(run.status, 'success', run.message)
        dp = DeviceProduct.objects.get()
        self.assertEqual(dp.stock, 22)
        self.assertEqual(list(dp.lanes.order_by('lane_number').values_list('stock', flat=True)), [8, 14])
        self.assertEqual(dp.source_currency, '')
        self.assertTrue(dp.template_url)
        brand = Brand.objects.create(code='test', name='Local brand')
        model = PhoneModel.objects.create(code='test-phone', name='Local phone', brand=brand, preview_family='iphone')
        product = dp.product
        product.phone_model, product.display_name, product.active = model, 'Local display', True
        product.save()
        dp.low_stock_threshold, dp.active = 25, False
        dp.save()
        self.rows[0]['surplus_stock'] = 7
        run = self.sync()
        dp.refresh_from_db(); product.refresh_from_db()
        self.assertEqual((dp.stock, dp.low_stock_threshold, dp.active), (21, 25, False))
        self.assertEqual((product.phone_model_id, product.display_name, product.active), (model.id, 'Local display', True))
        self.assertEqual((SupplierProduct.objects.count(), DeviceProduct.objects.count(), DeviceLaneStock.objects.count()), (1, 1, 2))
        self.assertEqual(run.changes, [{'goods_id': '171', 'before': 22, 'after': 21}])
        self.assertEqual(self.provider.detail.call_count, 1)

    def test_invalid_snapshots_never_replace_previous_inventory(self):
        self.sync()
        old_time = Device.objects.get(pk=self.device.id).last_success_at
        wrong_scope = lane(shop=999)
        duplicate = [lane(), lane()]
        bad_stock = lane(stock=-1)
        conflicting = lane(101, '9', 14); conflicting['specs'][0]['spec_value'] = 'Different phone'
        for rows in ([], [wrong_scope], duplicate, [bad_stock], [lane()], [lane(), conflicting], [{'bad': 'row'}]):
            with self.subTest(rows=rows):
                self.rows = rows
                run = self.sync()
                self.assertEqual(run.status, 'failed')
                self.assertEqual(DeviceProduct.objects.get().stock, 22)
                self.assertEqual(DeviceLaneStock.objects.count(), 2)
                self.assertEqual(Device.objects.get(pk=self.device.id).last_success_at, old_time)

    def test_template_failure_does_not_fabricate_template_or_lose_inventory(self):
        self.provider.detail.side_effect = ProviderError('模板查询失败')
        run = self.sync()
        self.assertEqual(run.status, 'success')
        self.assertIn('模板待补充', run.message)
        self.assertEqual(DeviceProduct.objects.get().template_url, '')
        self.assertEqual(DeviceProduct.objects.get().stock, 22)

    def test_stock_sync_adds_and_links_models_without_publishing_or_duplicates(self):
        for row in self.rows:
            row.update(product_name='iPhone 17', product_brand_name='iPhone')
            row['specs'][0]['spec_value'] = '17 Pro'
        run = self.sync()
        self.assertEqual(run.status, 'success', run.message)
        product = SupplierProduct.objects.get(goods_id='171')
        self.assertEqual(product.phone_model.name, 'iPhone 17 Pro')
        self.assertFalse(product.phone_model.active)
        self.assertFalse(product.phone_model.print_ready)
        self.assertFalse(product.active)
        self.assertIn('新增 1 个机型', run.message)
        audits = AuditLog.objects.filter(resource='management_api.supplierproduct', object_id=str(product.pk))
        self.assertEqual(audits.count(), 1)
        model_count = PhoneModel.objects.count()
        self.assertEqual(self.sync().status, 'success')
        self.assertEqual(PhoneModel.objects.count(), model_count)
        self.assertEqual(audits.count(), 1)
        # A new SKU for an existing model links to the same model on the next refresh.
        another = copy.deepcopy(self.rows[0])
        another.update(id=102, device_box_num='10', goods_id=172)
        self.rows.append(another)
        self.assertEqual(self.sync().status, 'success')
        self.assertEqual(SupplierProduct.objects.get(goods_id='172').phone_model_id, product.phone_model_id)
        self.assertEqual(PhoneModel.objects.count(), model_count)

    def test_unrecognized_models_keep_stock_and_report_manual_review(self):
        run = self.sync()
        self.assertEqual(run.status, 'success')
        self.assertIn('待确认 1 个', run.message)
        self.assertIsNone(SupplierProduct.objects.get().phone_model_id)
        self.assertEqual(DeviceProduct.objects.get().stock, 22)

    def test_catalog_failure_rolls_back_inventory_and_created_models(self):
        for row in self.rows:
            row.update(product_name='iPhone 17', product_brand_name='iPhone')
            row['specs'][0]['spec_value'] = '17 Pro'
        model_count = PhoneModel.objects.count()
        with patch('management_api.inventory_sync.AuditLog.objects.create', side_effect=RuntimeError('private error')):
            run = self.sync()
        self.assertEqual(run.status, 'failed')
        self.assertNotIn('private error', run.message)
        self.assertEqual(PhoneModel.objects.count(), model_count)
        self.assertFalse(SupplierProduct.objects.exists())
        self.assertFalse(DeviceProduct.objects.exists())

    def test_reused_goods_id_cannot_silently_change_mapped_specification(self):
        self.sync()
        for row in self.rows:
            row['specs'][0]['spec_value'] = 'Another model'
        run = self.sync()
        self.assertEqual(run.status, 'failed')
        self.assertIn('规格发生变化', run.message)
        self.assertEqual(SupplierProduct.objects.get().specs[0]['spec_value'], 'Example Pro')
        self.assertEqual(DeviceProduct.objects.get().stock, 22)

    def test_single_device_lease_blocks_duplicate_sync(self):
        def concurrent(_):
            with self.assertRaises(SyncBusy):
                sync_device(self.device.id)
            return copy.deepcopy(self.rows)
        self.provider.lanes.side_effect = concurrent
        self.assertEqual(self.sync().status, 'success')
        self.assertEqual(InventorySyncRun.objects.count(), 1)

    def test_configuration_change_during_fetch_does_not_publish(self):
        def changed(_):
            DeviceProviderConnection.objects.filter(pk=self.connection.pk).update(revision=2)
            return copy.deepcopy(self.rows)
        self.provider.lanes.side_effect = changed
        self.assertEqual(self.sync().status, 'failed')
        self.assertFalse(DeviceProduct.objects.exists())

    def test_publish_failure_is_atomic_and_error_is_redacted(self):
        with patch('management_api.inventory_sync.DeviceLaneStock.objects.update_or_create', side_effect=RuntimeError('secret transport header')):
            run = self.sync()
        self.assertEqual(run.status, 'failed')
        self.assertNotIn('secret', run.message)
        self.assertFalse(SupplierProduct.objects.exists())
        self.assertFalse(DeviceProduct.objects.exists())

    def test_same_vendor_ids_are_isolated_across_connections(self):
        self.sync()
        other = DeviceProviderConnection.objects.create(name='Other environment', base_url='https://shop.autovendpro.com',
            shop_id='146', api_key_ciphertext=encrypt_api_key('other-test-key'))
        self.device = Device.objects.create(connection=other, vendor_device_id='401', name='Other device')
        self.assertEqual(self.sync().status, 'success')
        self.assertEqual(SupplierProduct.objects.count(), 2)
        self.assertEqual(DeviceProduct.objects.count(), 2)

    def test_read_permissions_and_write_boundaries(self):
        self.sync()
        dp = DeviceProduct.objects.get()
        self.client.force_authenticate(self.reader)
        for path in ['devices', 'inventory/products', 'inventory/stocks', 'inventory/sync-runs', 'inventory/options']:
            self.assertEqual(self.client.get('/api/v1/admin/'+path+'/').status_code, 200, path)
        self.assertEqual(self.client.get('/api/v1/admin/device-connections/').status_code, 403)
        self.assertEqual(self.client.patch(f'/api/v1/admin/inventory/stocks/{dp.pk}/', {'low_stock_threshold': 5}).status_code, 403)
        with patch('management_api.inventory.sync_device') as mocked:
            self.assertEqual(self.client.post(f'/api/v1/admin/devices/{self.device.pk}/sync/').status_code, 403)
            mocked.assert_not_called()
        self.client.force_authenticate(self.root)
        self.assertEqual(self.client.patch(f'/api/v1/admin/inventory/stocks/{dp.pk}/', {'stock': 200}, format='json').status_code, 400)
        self.assertEqual(self.client.delete(f'/api/v1/admin/devices/{self.device.pk}/').status_code, 405)
        self.assertEqual(self.client.post('/api/v1/admin/inventory/products/', {}).status_code, 405)

    def test_anonymous_and_staff_without_permissions_are_denied(self):
        for user in (None, User.objects.create_user('no-grants', is_staff=True)):
            self.client.force_authenticate(user)
            for path in ['devices', 'inventory/products', 'inventory/stocks', 'inventory/sync-runs', 'inventory/options', 'device-connections']:
                self.assertEqual(self.client.get('/api/v1/admin/'+path+'/').status_code, 403, path)

    def test_connection_encryption_redaction_and_revision(self):
        key = 'only-test-key-never-a-real-credential'
        r = self.client.post('/api/v1/admin/device-connections/', {'name': 'New', 'base_url': 'https://shop.autovendpro.com',
            'shop_id': '999', 'authorization': key}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertNotIn(key, json.dumps(r.data))
        c = DeviceProviderConnection.objects.get(pk=r.data['id'])
        self.assertNotEqual(c.api_key_ciphertext, key)
        self.assertEqual(DeviceProvider(c).authorization, key)
        url = f'/api/v1/admin/device-connections/{c.pk}/'
        self.assertEqual(self.client.patch(url, {'name': 'Updated', 'revision': 1}, format='json').status_code, 200)
        self.assertEqual(self.client.patch(url, {'name': 'Stale', 'revision': 1}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(url, {'base_url': 'https://shop.widermatrix.cn', 'revision': 2}, format='json').status_code, 400)
        self.assertFalse(AuditLog.objects.filter(summary__contains=key).exists())
        self.assertNotIn('api_key_ciphertext', json.dumps(self.client.get(url).data))

    def test_connection_rejects_unapproved_origin_and_header_injection(self):
        body = {'name': 'Bad', 'shop_id': '146', 'authorization': 'test-key', 'base_url': 'http://127.0.0.1'}
        self.assertEqual(self.client.post('/api/v1/admin/device-connections/', body, format='json').status_code, 400)
        body.update(base_url='https://shop.widermatrix.cn', authorization='key\r\nInjected: bad')
        self.assertEqual(self.client.post('/api/v1/admin/device-connections/', body, format='json').status_code, 400)

    def test_disabled_device_does_not_contact_vendor(self):
        Device.objects.filter(pk=self.device.pk).update(active=False)
        with patch('management_api.inventory_sync.DeviceProvider') as mocked:
            with self.assertRaises(ProviderError):
                sync_device(self.device.pk)
            mocked.assert_not_called()

    def test_inventory_filters_expiry_and_safe_updates(self):
        self.sync()
        dp = DeviceProduct.objects.get()
        url = f'/api/v1/admin/inventory/stocks/{dp.pk}/'
        r = self.client.patch(url, {'low_stock_threshold': 23, 'active': False}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['stock'], 22)
        self.assertEqual(self.client.get('/api/v1/admin/inventory/stocks/?state=low').data['count'], 1)
        DeviceProduct.objects.filter(pk=dp.pk).update(observed_at=timezone.now()-timedelta(minutes=16))
        r = self.client.get('/api/v1/admin/inventory/stocks/?state=stale')
        self.assertEqual(r.data['count'], 1)
        self.assertTrue(r.data['results'][0]['stale'])
        self.assertEqual(self.client.get('/api/v1/admin/inventory/stocks/?device=invalid').status_code, 400)

    def test_mapping_requires_phone_model_and_ignores_no_supplier_fields(self):
        self.sync()
        p = SupplierProduct.objects.get()
        url = f'/api/v1/admin/inventory/products/{p.pk}/'
        self.assertEqual(self.client.patch(url, {'active': True}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(url, {'goods_id': '999'}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(url, {'display_name': 'My name'}, format='json').status_code, 200)

    def test_sync_permission_is_distinct_and_audited(self):
        operator = User.objects.create_user('sync-operator', is_staff=True)
        operator.user_permissions.add(Permission.objects.get(codename='sync_device'))
        self.client.force_authenticate(operator)
        with patch('management_api.inventory_sync.DeviceProvider', return_value=self.provider):
            r = self.client.post(f'/api/v1/admin/devices/{self.device.pk}/sync/', {}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['status'], 'success')
        self.assertTrue(AuditLog.objects.filter(action='sync', actor=operator).exists())

    def test_transport_checks_business_code_and_disables_redirects(self):
        def response(code):
            r = MagicMock()
            r.__enter__.return_value = r
            r.status_code = 200
            r.iter_content.return_value = [json.dumps({'code': code, 'message': 'secret response', 'data': []}).encode()]
            return r
        with patch('management_api.device_provider.requests.get', return_value=response(401)) as get:
            with self.assertRaisesMessage(ProviderError, '未授权'):
                DeviceProvider(self.connection).lanes('401')
            self.assertFalse(get.call_args.kwargs['allow_redirects'])
        with patch('management_api.device_provider.requests.get', return_value=response(200)):
            self.assertEqual(DeviceProvider(self.connection).lanes('401'), [])

    def test_session_mutations_require_csrf(self):
        c = APIClient(enforce_csrf_checks=True)
        c.force_login(self.root)
        self.assertEqual(c.post(f'/api/v1/admin/devices/{self.device.pk}/sync/', {}).status_code, 403)
