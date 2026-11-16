import uuid
import hashlib
from io import StringIO, BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch
from PIL import Image, ImageDraw
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from datetime import timedelta
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from .models import Brand, PhoneModel, DeviceProviderConnection, Device, SupplierProduct, DeviceProduct, PrintOrder, PhoneColor, PhoneColorResource
from .store_catalog import stock_template
from .orders import Snapshot


class StockCatalogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_catalog', stdout=StringIO())

    def setUp(self):
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        override = override_settings(MEDIA_ROOT=media.name)
        override.enable()
        self.addCleanup(override.disable)
        network = patch('requests.sessions.Session.request', side_effect=AssertionError('external network forbidden'))
        network.start()
        self.addCleanup(network.stop)
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

    def color(self, code='natural', **kwargs):
        color = PhoneColor.objects.create(phone_model=self.model, code=code, name=code,
                                         rgb={'r': 10, 'g': 120, 'b': 230}, active=True, **kwargs)
        image = Image.new('RGBA', (600, 1200), (120, 30, 80, 255))
        ImageDraw.Draw(image).rectangle((150, 300, 450, 900), fill=(0, 0, 0, 0))
        output = BytesIO(); image.save(output, format='PNG'); raw = output.getvalue()
        prefix = 'phone-colors/' + uuid.uuid4().hex
        paths = [default_storage.save(f'{prefix}/{role}.png', ContentFile(raw)) for role in ('overlay', 'mask')]
        resource = PhoneColorResource.objects.create(color=color, version=1,
            template_id=stock_template(self.stock)['id'], width=600, height=1200,
            overlay=paths[0], mask=paths[1], overlay_sha256=hashlib.sha256(raw).hexdigest(),
            mask_sha256=hashlib.sha256(raw).hexdigest(), verified_at=timezone.now())
        color.current_resource=resource; color.save()
        return color

    def test_optional_colors_are_ordered_and_admin_rgb_edits_reach_public_catalog(self):
        self.assertEqual(self.catalog()['models'][0]['colors'], [])
        color = self.color(sort_order=10, is_default=True)
        self.color('first', sort_order=1)
        result = self.catalog()
        self.assertEqual([c['code'] for c in result['models'][0]['colors']], ['first', 'natural'])
        self.assertTrue(result['models'][0]['colors'][1]['isDefault'])
        self.assertEqual(result['templates'][0], stock_template(self.stock))
        admin = APIClient(); admin.force_authenticate(User.objects.create_superuser('synthetic-admin'))
        edited = admin.patch(f'/api/v1/admin/phone-colors/{color.pk}/', {'rgb': {'r': 9, 'g': 8, 'b': 7}}, format='json')
        self.assertEqual(edited.status_code, 200, edited.data)
        exposed = self.catalog()['models'][0]['colors'][1]
        self.assertEqual(exposed['rgb'], {'r': 9, 'g': 8, 'b': 7})
        self.assertNotIn('verified_by', str(result))
        self.assertNotIn('sha256', str(result))

    def test_colors_follow_each_case_style_template_without_hiding_unconfigured_styles(self):
        self.color()
        magnetic_product = SupplierProduct.objects.create(
            connection=self.connection, goods_id='magnetic', product_id='magnetic',
            phone_model=self.model, active=True, specs=[{'spec_name': '版本', 'spec_value': '磁吸款'}])
        magnetic = DeviceProduct.objects.create(
            device=self.device, product=magnetic_product, stock=4, observed_at=timezone.now(),
            template_url=self.stock.template_url, template_imported_url=self.stock.template_url,
            template_image=self.stock.template_image, template_mask=self.stock.template_mask,
            template_width=600, template_height=1200)
        for params in [None, {}]:
            model = next(m for m in self.catalog(params)['models'] if m['name'] == self.model.name)
            standard, magnet = model['styles']
            self.assertEqual([c['code'] for c in standard['colors']], ['natural'])
            self.assertEqual(magnet['colors'][0]['previewMode'], 'rgb')
            self.assertIsNone(magnet['colors'][0]['resource'])
            self.assertTrue(magnet['available'])
            self.assertEqual(magnet['templateId'], stock_template(magnetic)['id'])
            self.assertNotEqual(standard['templateId'], magnet['templateId'])
        valid = Snapshot(data={**self.snapshot, 'caseMaterial': 'standard',
                               'phoneColor': {'code': 'natural', 'version': 1}})
        self.assertTrue(valid.is_valid(), valid.errors)
        invalid = Snapshot(data={**self.snapshot, 'caseMaterial': 'magnetic',
                                 'phoneTemplateId': stock_template(magnetic)['id'],
                                 'phoneColor': {'code': 'natural', 'version': 1}})
        self.assertFalse(invalid.is_valid(), 'A color from another style template must not be accepted.')

    def test_inactive_unverified_missing_mismatched_and_corrupt_colors_do_not_hide_base_model(self):
        color = self.color(); resource = color.current_resource
        changes = [('active', False), ('rgb', {'r': True, 'g': 0, 'b': 0})]
        for field, value in changes:
            original = getattr(color, field)
            PhoneColor.objects.filter(pk=color.pk).update(**{field: value})
            self.assertEqual(self.catalog()['models'][0]['colors'], [], field)
            PhoneColor.objects.filter(pk=color.pk).update(**{field: original})
        for field, value in [('verified_at', None), ('template_id', 'other'), ('width', 42), ('overlay', '../private.png'), ('overlay_sha256', '0'*64)]:
            original = getattr(resource, field)
            PhoneColorResource.objects.filter(pk=resource.pk).update(**{field: value})
            self.assertIsNone(self.catalog()['models'][0]['colors'][0]['resource'], field)
            PhoneColorResource.objects.filter(pk=resource.pk).update(**{field: original})
        default_storage.delete(resource.mask)
        self.assertIsNone(self.catalog()['models'][0]['colors'][0]['resource'])
        self.assertEqual(self.catalog()['templates'][0], stock_template(self.stock))
        # Even a matching hash cannot turn invalid image bytes into a preview.
        with default_storage.open(resource.mask, 'wb') as output:
            output.write(b'not-a-png')
        PhoneColorResource.objects.filter(pk=resource.pk).update(mask_sha256=hashlib.sha256(b'not-a-png').hexdigest())
        self.assertIsNone(self.catalog()['models'][0]['colors'][0]['resource'])

    def test_rgb_only_colors_work_without_resources_and_freeze_server_values(self):
        color = PhoneColor.objects.create(phone_model=self.model, code='rgb-only', name='RGB only',
                                          rgb={'r': 11, 'g': 22, 'b': 33}, active=True)
        exposed = self.catalog()['models'][0]['colors'][0]
        self.assertEqual(exposed['previewMode'], 'rgb')
        self.assertIsNone(exposed['resource'])
        valid = Snapshot(data={**self.snapshot, 'phoneColor': {'code': color.code, 'version': 0, 'rgb': color.rgb}})
        self.assertTrue(valid.is_valid(), valid.errors)
        self.assertEqual(valid.validated_data['phoneColor'], exposed)
        for changes in [{'rgb': {'r': 0, 'g': 0, 'b': 0}}, {'rgb': {'r': True, 'g': 22, 'b': 33}}, {'version': 1}, {'code': 'foreign'}]:
            selection = {'code': color.code, 'version': 0, 'rgb': color.rgb, **changes}
            invalid = Snapshot(data={**self.snapshot, 'phoneColor': selection})
            self.assertFalse(invalid.is_valid(), selection)
        DeviceProduct.objects.filter(pk=self.stock.pk).update(template_image='', template_mask='')
        record = next(m for m in self.catalog({})['models'] if m['name'] == self.model.name)
        self.assertTrue(all(style['colors'][0]['rgb'] == color.rgb for style in record['styles']))
        self.assertEqual(self.catalog()['models'], [])  # RGB does not authorize device printing.

    def test_colors_do_not_make_zero_stock_or_missing_template_saleable(self):
        self.color()
        DeviceProduct.objects.filter(pk=self.stock.pk).update(stock=0)
        self.assertEqual(self.catalog()['models'], [])
        DeviceProduct.objects.filter(pk=self.stock.pk).update(stock=3, template_mask='')
        self.assertEqual(self.catalog()['models'], [])

    def test_color_selection_is_server_resolved_and_invalid_or_forged_versions_are_rejected(self):
        color = self.color()
        snapshot = {**self.snapshot, 'phoneColor': {'code': color.code, 'version': 1}}
        valid = Snapshot(data=snapshot); self.assertTrue(valid.is_valid(), valid.errors)
        self.assertEqual(valid.validated_data['phoneColor'], self.catalog()['models'][0]['colors'][0])
        for selection in ({'code': 'absent', 'version': 1}, {'code': color.code, 'version': 2},
                          {'code': color.code, 'version': True}, {'code': color.code, 'version': '1'},
                          {'code': color.code, 'version': 1, 'rgb': {'r': 0, 'g': 0, 'b': 0}}):
            invalid = Snapshot(data={**self.snapshot, 'phoneColor': selection})
            self.assertFalse(invalid.is_valid(), selection)
        PhoneColor.objects.filter(pk=color.pk).update(active=False)
        self.assertFalse(Snapshot(data=snapshot).is_valid())
        self.assertTrue(Snapshot(data=self.snapshot).is_valid())
        client = APIClient(); client.credentials(HTTP_X_ORDER_KEY='a'*64)
        response = client.post('/api/v1/store/orders/', {'request_key': str(uuid.uuid4()), 'accepted': True,
            'expected_amount': '10.00', 'snapshot': snapshot}, format='json')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(PrintOrder.objects.exists())

    def test_order_freezes_color_and_resource_without_mutating_historical_snapshot(self):
        color = self.color()
        client=APIClient(); client.credentials(HTTP_X_ORDER_KEY='a'*64)
        body={'request_key':str(uuid.uuid4()), 'accepted':True, 'expected_amount':'10.00',
              'snapshot':{**self.snapshot, 'phoneColor':{'code':color.code,'version':1}}}
        response=client.post('/api/v1/store/orders/', body, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        reference=response.data['reference']; frozen=response.data['snapshot']['phoneColor']
        original=PrintOrder.objects.get(reference=reference)
        self.assertEqual(original.snapshot['phoneColor'], frozen)
        PhoneColor.objects.filter(pk=color.pk).update(rgb={'r':0,'g':0,'b':0}, active=False)
        resource=color.current_resource; resource.pk=None; resource.version=2; resource.save()
        PhoneColor.objects.filter(pk=color.pk).update(current_resource=resource)
        PrintOrder.objects.filter(pk=original.pk).update(status='paid')
        read=client.get(f'/api/v1/store/orders/{reference}/')
        self.assertEqual(read.data['snapshot']['phoneColor'], frozen)
        self.assertEqual(read.data['amount'], response.data['amount'])
        retried=client.post('/api/v1/store/orders/', body, format='json')
        self.assertEqual(retried.status_code, 200, retried.data)
        self.assertEqual(retried.data['snapshot']['phoneColor'], frozen)
        self.assertEqual(PrintOrder.objects.count(), 1)
        other=APIClient(); other.credentials(HTTP_X_ORDER_KEY='b'*64)
        self.assertEqual(other.get(f'/api/v1/store/orders/{reference}/').status_code, 404)

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
