import tempfile
from unittest.mock import patch
from cryptography.fernet import Fernet
from django.test import TestCase, override_settings
from . import test_inventory
from .test_inventory import lane
from .test_supplier_templates import png
from .models import DeviceProduct, PhoneModel, Brand
from .supplier_templates import TemplateError
from .inventory import ProductSerializer
from .serializers import PhoneModelSerializer, BrandSerializer
from .store_catalog import store_models


@override_settings(AI_CONFIG_ENCRYPTION_KEY=Fernet.generate_key().decode())
class AutoPublishTests(TestCase):
    sync = test_inventory.InventoryTests.sync

    def setUp(self):
        test_inventory.InventoryTests.setUp(self)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        override = override_settings(MEDIA_ROOT=folder.name)
        override.enable(); self.addCleanup(override.disable)
        self.rows = [lane()]
        self.rows[0].update(product_brand_name='Google', product_name='Google Pixel 11',
            specs=[{'spec_name':'型号','spec_value':'Pixel 11 Pro XL'}],
            template_url='https://file.autovendpro.com/one.png')

    def test_sync_publishes_new_google_and_refreshes_template_without_duplicates(self):
        with patch('management_api.supplier_templates.download_template', return_value=png()) as download:
            self.assertEqual(self.sync().status, 'success')
            stock = DeviceProduct.objects.select_related('product__phone_model__brand').get()
            model = stock.product.phone_model
            self.assertEqual(model.name, 'Google Pixel 11 Pro XL')
            self.assertTrue(model.active and model.brand.active and stock.product.active)
            self.assertFalse(model.print_ready)
            self.assertTrue(stock.template_mask)
            self.assertEqual(len(store_models({'device_id':'401','shop_id':'146'})['models']), 1)
            self.sync()
            self.assertEqual(download.call_count, 1)
            self.rows[0]['template_url'] = 'https://file.autovendpro.com/two.png'
            self.sync()
            self.assertEqual(download.call_count, 2)
            self.assertEqual(PhoneModel.objects.count(), 1)
            self.rows[0]['surplus_stock'] = 0
            self.sync()
            self.assertEqual(store_models({})['models'], [])

    def test_failed_template_retries_and_does_not_expose_incomplete_model(self):
        with patch('management_api.supplier_templates.download_template', side_effect=TemplateError('暂不可用')):
            self.assertEqual(self.sync().status, 'success')
        self.assertEqual(store_models({})['models'], [])
        with patch('management_api.supplier_templates.download_template', return_value=png()):
            self.sync()
        self.assertEqual(len(store_models({})['models']), 1)

    def test_manual_disable_while_pending_is_not_undone(self):
        for kind, serializer in [('product', ProductSerializer), ('model', PhoneModelSerializer), ('brand', BrandSerializer)]:
            with self.subTest(kind=kind):
                with patch('management_api.supplier_templates.download_template', side_effect=TemplateError('暂不可用')):
                    self.sync()
                stock = DeviceProduct.objects.select_related('product__phone_model__brand').get()
                obj = {'product':stock.product, 'model':stock.product.phone_model,
                       'brand':stock.product.phone_model.brand}[kind]
                edit = serializer(obj, data={'active':False}, partial=True)
                self.assertTrue(edit.is_valid(), edit.errors); edit.save()
                with patch('management_api.supplier_templates.download_template', return_value=png()):
                    self.sync()
                obj.refresh_from_db()
                self.assertFalse(obj.active)
                self.assertFalse(obj.auto_publish_pending)
                self.assertEqual(store_models({})['models'], [])
                # Restore for the next independent manual override.
                obj.active = True; obj.save()

    def test_existing_manually_disabled_model_and_mapping_are_preserved(self):
        brand=Brand.objects.create(code='google',name='Google')
        model=PhoneModel.objects.create(code='pixel',name='Google Pixel 11 Pro XL',brand=brand,active=False)
        with patch('management_api.supplier_templates.download_template', return_value=png()):
            self.sync()
        model.refresh_from_db()
        self.assertFalse(model.active)
        self.assertEqual(store_models({})['models'], [])

    def test_changed_template_failure_hides_old_template_until_recovered(self):
        with patch('management_api.supplier_templates.download_template', return_value=png()):
            self.sync()
        self.rows[0]['template_url'] = 'https://file.autovendpro.com/changed.png'
        with patch('management_api.supplier_templates.download_template', side_effect=TemplateError('暂不可用')):
            self.sync()
        self.assertEqual(store_models({})['models'], [])
        with patch('management_api.supplier_templates.download_template', return_value=png()):
            self.sync()
        self.assertEqual(len(store_models({})['models']), 1)

    def test_pixel_variants_are_distinct_and_unknown_models_remain_unpublished(self):
        from types import SimpleNamespace
        from .inventory_catalog import model_identity
        for name in ('Pixel 11', 'Pixel 11 Pro', 'Pixel 11 Pro XL', 'Pixel 10a', 'Pixel 10 Pro Fold'):
            product = SimpleNamespace(brand_name='Google', specs=[{'spec_name':'型号', 'spec_value':name}])
            self.assertEqual(model_identity(product)[1], 'Google '+name)
        self.rows[0]['specs'] = [{'spec_name':'型号','spec_value':'unknown'}]
        with patch('management_api.supplier_templates.download_template') as download:
            self.sync()
        download.assert_not_called()
        self.assertEqual(store_models({})['models'], [])
