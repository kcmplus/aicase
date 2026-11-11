import uuid
from io import StringIO
from datetime import timedelta
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from .models import Brand, PhoneModel, DeviceProviderConnection, Device, SupplierProduct, DeviceProduct, PrintOrder
from .store_catalog import stock_template
from .orders import Snapshot


class StockCatalogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_catalog', stdout=StringIO())

    def setUp(self):
        self.model = PhoneModel.objects.create(code='new-phone', name='iPhone 18', brand=Brand.objects.get(code='apple'), preview_family='iphone')
        self.connection = DeviceProviderConnection.objects.create(name='Vendor', base_url='https://shop.widermatrix.cn', shop_id='146')
        self.device = Device.objects.create(connection=self.connection, vendor_device_id='401', name='Device', sync_status='success')
        self.product = SupplierProduct.objects.create(connection=self.connection, goods_id='1', product_id='1', phone_model=self.model, active=True, specs=[{'spec_name':'版本','spec_value':'普通款'}])
        self.stock = DeviceProduct.objects.create(device=self.device, product=self.product, stock=3, observed_at=timezone.now(),
            template_url='https://oss.widermatrix.cn/a.png', template_imported_url='https://oss.widermatrix.cn/a.png',
            template_image='supplier-templates/'+'a'*64+'-overlay.png', template_mask='supplier-templates/'+'b'*64+'-mask.png', template_width=600, template_height=1200)
        self.snapshot = {'version':2,'code':'POP-C-0123456789ABCDEF','source':'collection','designId':'bloom',
            'model':self.model.name,'phoneTemplateId':stock_template(self.stock)['id'],'photo':'','effect':'original','intensity':65,'zoom':100,'x':50,'y':50}

    def catalog(self, params=None):
        r = self.client.get('/api/v1/store/phone-models/', {'device_id':'401','shop_id':'146'} if params is None else params)
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def test_public_catalog_only_exposes_usable_in_stock_choices(self):
        result = self.catalog()
        self.assertEqual([r['name'] for r in result['models']], [self.model.name])
        self.assertEqual(result['templates'][0]['mask'], '/media/'+self.stock.template_mask)
        self.assertNotIn('oss.widermatrix.cn', str(result))
        self.assertNotIn('api_key', str(result))
        self.assertTrue(result['templates'][0]['previewOnly'])
        self.assertIsNone(result['templates'][0]['dpi'])
        self.assertIn('no-store', self.client.get('/api/v1/store/phone-models/')['Cache-Control'])

    def test_zero_stale_disabled_missing_assets_and_changed_source_are_hidden(self):
        fields = [('stock', 0), ('active', False), ('present', False), ('template_mask', ''),
                  ('template_image', ''), ('template_imported_url', 'https://oss.widermatrix.cn/old.png'),
                  ('observed_at', timezone.now()-timedelta(minutes=16))]
        for field, value in fields:
            original = getattr(self.stock, field)
            DeviceProduct.objects.filter(pk=self.stock.pk).update(**{field: value})
            self.assertEqual(self.catalog()['models'], [], field)
            DeviceProduct.objects.filter(pk=self.stock.pk).update(**{field: original})
        for obj in (self.product, self.model, self.model.brand, self.device, self.connection):
            obj.active=False; obj.save()
            self.assertEqual(self.catalog()['models'], [], str(obj))
            obj.active=True; obj.save()

    def test_refresh_does_not_hide_fresh_snapshot_and_expiry_is_not_reported_as_sold_out(self):
        for status in ('running', 'failed'):
            self.device.sync_status=status; self.device.save()
            self.assertEqual(len(self.catalog()['models']), 1)
        DeviceProduct.objects.filter(pk=self.stock.pk).update(observed_at=timezone.now()-timedelta(minutes=16))
        self.assertEqual(self.catalog()['availability'], 'updating')
        self.assertEqual(self.catalog()['models'], [])
        self.assertEqual(self.catalog({'device_id':'999'})['availability'], 'empty')
        DeviceProduct.objects.filter(pk=self.stock.pk).update(stock=0)
        self.assertEqual(self.catalog()['availability'], 'empty')

    def test_device_scope_never_falls_back_to_another_device(self):
        self.assertEqual(len(self.catalog({'device_id':'401','shop_id':'146'})['models']), 1)
        self.assertEqual(self.catalog({'device_id':'999'})['models'], [])
        self.assertEqual(self.catalog({'device_id':'401','shop_id':'999'})['models'], [])
        self.assertEqual(self.client.get('/api/v1/store/phone-models/', {'device_id':'bad'}).status_code, 400)
        other = DeviceProviderConnection.objects.create(name='Other', base_url='https://shop.autovendpro.com', shop_id='200')
        Device.objects.create(connection=other, vendor_device_id='401', name='Other device')
        self.assertEqual(self.client.get('/api/v1/store/phone-models/', {'device_id':'401'}).status_code, 400)

    def test_shared_model_is_deduplicated_without_mixing_device_stock(self):
        other = Device.objects.create(connection=self.connection, vendor_device_id='402', name='Other device', sync_status='success')
        self.stock.pk=None; self.stock.device=other; self.stock.save()
        self.assertEqual([r['name'] for r in self.catalog({})['models']].count(self.model.name), 1)
        DeviceProduct.objects.filter(device=self.device).update(stock=0)
        self.assertIn(self.model.name, [r['name'] for r in self.catalog({})['models']])
        self.assertEqual(self.catalog({'device_id':'401'})['models'], [])

    def test_checkout_rechecks_stock_and_rejects_wrong_template_or_client_assets(self):
        valid = Snapshot(data=self.snapshot); self.assertTrue(valid.is_valid(), valid.errors)
        self.assertEqual(valid.validated_data['_inventory_item'], self.stock.pk)
        for changes in ({'phoneTemplateId':'supplier-999-'+'a'*20}, {'_template':{}}, {'model':'iPhone 17'}):
            invalid = Snapshot(data={**self.snapshot, **changes}); self.assertFalse(invalid.is_valid())
        DeviceProduct.objects.filter(pk=self.stock.pk).update(stock=0)
        invalid = Snapshot(data=self.snapshot); self.assertFalse(invalid.is_valid())

    def test_frozen_order_template_survives_stock_and_template_changes(self):
        client=APIClient(); client.credentials(HTTP_X_ORDER_KEY='a'*64)
        response=client.post('/api/v1/store/orders/', {'request_key':str(uuid.uuid4()),'accepted':True,
            'expected_amount':'10.00','snapshot':self.snapshot}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        original = response.data['phone_template']
        DeviceProduct.objects.filter(pk=self.stock.pk).update(stock=0,template_image='supplier-templates/'+'c'*64+'-overlay.png')
        order = PrintOrder.objects.get()
        read = client.get(f'/api/v1/store/orders/{order.reference}/')
        self.assertEqual(read.status_code, 200)
        self.assertEqual(read.data['phone_template'], original)
        self.assertEqual(self.catalog()['models'], [])

    def test_unscoped_design_catalog_ignores_stock_location_and_template_availability(self):
        model = PhoneModel.objects.create(code='design-only', name='Design Only Phone', brand=self.model.brand)
        self.stock.stock = 0
        self.stock.observed_at = timezone.now() - timedelta(days=1)
        self.stock.save()
        self.device.active = False
        self.device.provider_profile = {}
        self.device.save()
        catalog = self.catalog({})
        self.assertEqual(catalog['scope'], 'catalog')
        records = {row['name']: row for row in catalog['models']}
        self.assertIn(self.model.name, records)
        self.assertIn(model.name, records)
        self.assertNotIn('templateId', records[model.name])
        self.assertIn('templateId', records[self.model.name])
        self.assertEqual(self.catalog()['models'], [])
        self.assertEqual(self.catalog()['scope'], 'device')
        self.stock.template_mask = ''
        self.stock.save()
        self.assertIn(self.model.name, [r['name'] for r in self.catalog({})['models']])
        model.active = False
        model.save()
        self.assertNotIn(model.name, [r['name'] for r in self.catalog({})['models']])
        # Being available for design is not authorization to sell/print absent stock.
        self.assertFalse(Snapshot(data=self.snapshot).is_valid())

    def test_unscoped_catalog_includes_different_models_across_devices(self):
        other_model = PhoneModel.objects.create(code='other-phone', name='Other Phone', brand=self.model.brand)
        device = Device.objects.create(connection=self.connection, vendor_device_id='402', name='Other')
        product = SupplierProduct.objects.create(connection=self.connection, goods_id='2', product_id='2', phone_model=other_model, active=True, specs=[{'spec_name':'版本','spec_value':'普通款'}])
        self.stock.pk = None
        self.stock.product = product
        self.stock.device = device
        self.stock.save()
        self.assertTrue({self.model.name, other_model.name}.issubset({r['name'] for r in self.catalog({})['models']}))
        self.assertEqual([r['name'] for r in self.catalog()['models']], [self.model.name])
        self.assertEqual([r['name'] for r in self.catalog({'device_id':'402','shop_id':'146'})['models']], [other_model.name])
