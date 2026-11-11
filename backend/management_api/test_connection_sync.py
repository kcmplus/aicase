from io import StringIO
from unittest.mock import patch
from django.core.management import call_command
from django.test import TestCase, override_settings
from cryptography.fernet import Fernet
from rest_framework.test import APIClient
from . import test_inventory_publish
from .test_supplier_templates import png
from .models import DeviceProduct, Device, PhoneModel, AuditLog
from .store_catalog import store_models
from .connection_sync import sync_connection
from .device_provider import ProviderError


@override_settings(AI_CONFIG_ENCRYPTION_KEY=Fernet.generate_key().decode())
class ConnectionSyncTests(TestCase):
    setUp = test_inventory_publish.AutoPublishTests.setUp
    sync = test_inventory_publish.AutoPublishTests.sync

    def profile_response(self, **kwargs):
        return {'page': 1, 'totalNum': 2, 'totalPages': 1, 'list': [
            {'id': 401, 'shop_id': 146, 'device_name': 'Supplier name'},
            {'id': 402, 'shop_id': 146, 'device_name': 'New inactive device'},
        ]}

    def test_connection_button_and_timer_both_publish_full_catalog(self):
        client = APIClient(); client.force_authenticate(self.root)
        with patch('management_api.device_discovery.DeviceProvider') as provider, \
                patch('management_api.inventory_sync.DeviceProvider', return_value=self.provider), \
                patch('management_api.supplier_templates.download_template', return_value=png()) as download:
            provider.return_value.devices.side_effect = self.profile_response
            response = client.post(f'/api/v1/admin/device-connections/{self.connection.pk}/sync-devices/', {}, format='json')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['status'], 'success')
            self.assertEqual(len(response.data['devices']), 1)
            self.assertEqual(len(store_models({'device_id': '401', 'shop_id': '146'})['models']), 1)
            self.assertFalse(Device.objects.get(vendor_device_id='402').active)
            self.rows[0]['surplus_stock'] = 3
            self.rows[0]['template_url'] = 'https://file.autovendpro.com/updated.png'
            call_command('sync_device_inventory', all=True, stdout=StringIO())
            self.assertEqual(provider.return_value.devices.call_count, 2)
            self.assertEqual(download.call_count, 2)
        stock = DeviceProduct.objects.get()
        self.assertEqual(stock.stock, 3)
        self.assertEqual(stock.template_imported_url, self.rows[0]['template_url'])
        self.assertEqual(PhoneModel.objects.count(), 1)
        self.assertTrue(AuditLog.objects.filter(actor=self.root, action='sync').exists())

    def test_partial_sync_reports_failure_without_skipping_other_devices(self):
        from types import SimpleNamespace
        other = Device.objects.create(connection=self.connection, vendor_device_id='403', name='Other')
        with patch('management_api.connection_sync.discover_devices', side_effect=ProviderError('资料暂不可用')), \
                patch('management_api.connection_sync.sync_device', side_effect=[ProviderError('库存暂不可用'), SimpleNamespace(status='success',message='ok')]) as sync:
            result = sync_connection(self.connection)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['profile']['status'], 'failed')
        self.assertEqual([x['status'] for x in result['devices']], ['failed', 'success'])
        self.assertEqual(sync.call_args.args[0], other.pk)

    def test_debug_and_disabled_connection_do_not_contact_supplier(self):
        with patch('management_api.connection_sync.discover_devices') as profile, patch('management_api.connection_sync.sync_device') as inventory:
            with override_settings(DIRECT_DEBUG_ENABLED=True), self.assertRaises(ProviderError):
                sync_connection(self.connection)
            self.connection.active = False
            with self.assertRaises(ProviderError): sync_connection(self.connection)
        profile.assert_not_called(); inventory.assert_not_called()

    def test_legacy_disabled_model_is_explained_and_only_explicit_enable_releases_it(self):
        from .inventory import ProductSerializer
        from .serializers import PhoneModelSerializer
        from .models import Brand
        brand = Brand.objects.create(code='google', name='Google')
        model = PhoneModel.objects.create(code='pixel', name='Google Pixel 11 Pro XL', brand=brand, active=False)
        with patch('management_api.supplier_templates.download_template', return_value=png()):
            run = self.sync()
            self.assertIn('机型停用 1 个', run.message)
            product = DeviceProduct.objects.get().product
            self.assertIn('机型已停用，需人工启用', ProductSerializer(product).data['publication_notes'])
            self.assertEqual(store_models({'device_id':'401','shop_id':'146'})['models'], [])
            edit = PhoneModelSerializer(model, data={'active': True}, partial=True)
            self.assertTrue(edit.is_valid()); edit.save()
            self.sync()
        product.refresh_from_db()
        self.assertTrue(product.active)
        self.assertEqual(len(store_models({'device_id':'401','shop_id':'146'})['models']), 1)
