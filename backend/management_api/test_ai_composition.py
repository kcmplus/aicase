from copy import deepcopy
from datetime import timedelta
from io import BytesIO
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw
from django.contrib.auth.models import User, Permission
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase, SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from .ai_composition import mask_regions, resolve_template, composition_snapshot, suggestion, RegionInput
from .models import Brand, PhoneModel, DeviceProviderConnection, Device, SupplierProduct, DeviceProduct
from .store_catalog import stock_template, available_stocks


def region_input(**changes):
    return dict(revision=0, template_id='', case_material='standard',
                safe={'x':20,'y':40,'width':60,'height':50},
                avoid=[{'x':0,'y':0,'width':100,'height':35}], margin=3,
                confirmed=False, source_url='', note='', **changes)


class MaskGeometryTests(SimpleTestCase):
    def test_wide_camera_and_bottom_rounding_leave_continuous_subject_area(self):
        alpha = Image.new('L', (600, 1200))
        ImageDraw.Draw(alpha).rectangle((18,378,582,1175),fill=255)
        result = mask_regions(alpha)
        self.assertEqual(result['safe'], {'x':20,'y':31.5,'width':60,'height':66.5})
        self.assertEqual(result['avoid'], [{'x':0,'y':0,'width':100,'height':31.5}])
        # An opaque hole inside the center band breaks the run, never treated as safe.
        ImageDraw.Draw(alpha).rectangle((295,500,305,600),fill=0)
        self.assertGreater(mask_regions(alpha)['safe']['y'], 50)
        self.assertIsNone(mask_regions(Image.new('L',(600,1200))))

    def test_automatic_edges_survive_editor_two_decimal_rounding(self):
        alpha = Image.new('L', (888, 1811))
        ImageDraw.Draw(alpha).rectangle((18,554,870,1776), fill=255)
        regions = mask_regions(alpha)
        body = region_input(); body.update(regions)
        # Horizontal drag rounds all four displayed coordinates to two decimals.
        body['safe'] = {k: round(v, 2) for k, v in body['safe'].items()}
        body['safe']['x'] += 1
        serializer = RegionInput(data=body)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_bounds_overlap_nan_and_unknown_fields_rejected(self):
        for field, value in [('safe',{'x':90,'y':40,'width':20,'height':50}),
                             ('safe',{'x':False,'y':40,'width':20,'height':50}),
                             ('avoid',[{'x':20,'y':40,'width':60,'height':50}]),
                             ('margin',float('nan')),('unexpected',True)]:
            body=region_input();body[field]=value
            self.assertFalse(RegionInput(data=body).is_valid(), (field,value))


class CompositionConfigurationTests(TestCase):
    def setUp(self):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup)
        override=override_settings(MEDIA_ROOT=temp.name);override.enable();self.addCleanup(override.disable)
        self.brand=Brand.objects.create(code='synthetic',name='Synthetic')
        self.model=PhoneModel.objects.create(code='synthetic-phone',name='Synthetic phone',brand=self.brand,active=True)
        connection=DeviceProviderConnection.objects.create(name='Fixture',base_url='https://shop.widermatrix.cn',shop_id='146')
        device=Device.objects.create(connection=connection,vendor_device_id='401',name='Fixture',sync_status='success')
        product=SupplierProduct.objects.create(connection=connection,goods_id='1',product_id='1',phone_model=self.model,active=True,specs=[{'spec_name':'版本','spec_value':'普通款'}])
        image=Image.new('RGBA',(600,1200));ImageDraw.Draw(image).rectangle((18,378,582,1175),fill=(255,255,255,255))
        raw=BytesIO();image.save(raw,format='PNG')
        mask=default_storage.save('supplier-templates/fixture-mask.png',ContentFile(raw.getvalue()))
        self.stock=DeviceProduct.objects.create(device=device,product=product,stock=0,observed_at=timezone.now()-timedelta(days=1),template_url='https://example.com/t.png',template_imported_url='https://example.com/t.png',template_image=mask,template_mask=mask,template_width=600,template_height=1200)
        self.template=stock_template(self.stock)
        self.url=f'/api/v1/admin/phone-models/{self.model.pk}/composition/'
        self.client=APIClient();self.admin=User.objects.create_superuser('fixture-admin')
        self.client.force_authenticate(self.admin)

    def test_saved_template_survives_stale_stock_without_granting_print_access(self):
        self.assertFalse(available_stocks().filter(pk=self.stock.pk).exists())
        self.assertEqual(resolve_template(self.model,'standard',self.template['id']),self.template)
        for material,template_id in [('magnetic',self.template['id']),('standard','supplier-wrong-revision')]:
            with self.assertRaises(ValidationError):resolve_template(self.model,material,template_id)
        other=PhoneModel.objects.create(code='other',name='Other',brand=self.brand)
        with self.assertRaises(ValidationError):resolve_template(other,'standard',self.template['id'])
        self.assertFalse(available_stocks().filter(pk=self.stock.pk).exists())

    def test_mask_measurement_and_fit_coordinates_use_same_full_canvas(self):
        region=suggestion(self.template)
        self.assertEqual(region['origin'],'preview_mask')
        snapshot=composition_snapshot(self.model,self.template,'standard',self.template['id'])
        # 2:3 foreground occupies y=12.5..87.5 in a 1:2 phone canvas.
        self.assertAlmostEqual(snapshot['image_safe']['y'], (31.5+3-12.5)/75*100,places=2)
        self.assertEqual(snapshot['image_safe']['width'],54)
        self.assertEqual(snapshot['fit'],'blur')

    def test_admin_permissions_validation_version_and_public_privacy(self):
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.url).status_code,(401,403))
        staff=User.objects.create_user('viewer',is_staff=True)
        self.client.force_authenticate(staff)
        self.assertEqual(self.client.get(self.url).status_code,403)
        staff.user_permissions.add(Permission.objects.get(codename='view_phonemodel'))
        self.client.force_authenticate(User.objects.get(pk=staff.pk))
        self.assertEqual(self.client.get(self.url).status_code,200)
        self.assertEqual(self.client.put(self.url,region_input(),format='json').status_code,403)
        self.client.force_authenticate(self.admin)
        body=region_input();body.update(template_id=self.template['id'],note='private-config-canary')
        result=self.client.put(self.url,body,format='json')
        self.assertEqual(result.status_code,200,result.data)
        self.assertEqual(result.data['revision'],1)
        self.assertEqual(self.client.put(self.url,body,format='json').status_code,409)
        self.model.refresh_from_db();self.assertEqual(self.model.composition_revision,1)
        before=deepcopy(self.model.composition_regions)
        invalid={**body,'revision':1,'avoid':[body['safe']]}
        self.assertEqual(self.client.put(self.url,invalid,format='json').status_code,400)
        self.model.refresh_from_db();self.assertEqual(self.model.composition_regions,before)
        public=self.client.get('/api/v1/store/phone-models/').json()
        self.assertNotIn('private-config-canary',str(public))
        self.assertNotIn('composition_regions',str(public))
        self.assertEqual(self.client.put(self.url,{**body,'revision':1,'reset':True},format='json').status_code,200)
        self.model.refresh_from_db();self.assertEqual(self.model.composition_regions,{})
        self.assertEqual(self.model.composition_revision,2)

    def test_no_template_uses_conservative_fallback_and_manual_settings_are_revision_specific(self):
        snapshot=composition_snapshot(self.model,None,'magnetic')
        self.assertEqual(snapshot['origin'],'conservative_fallback')
        body=region_input();body['template_id']=self.template['id']
        self.assertEqual(self.client.put(self.url,body,format='json').status_code,200)
        self.model.refresh_from_db()
        self.assertEqual(composition_snapshot(self.model,self.template,'standard')['origin'],'manual')
        newer={**self.template,'id':self.template['id']+'-new'}
        self.assertEqual(composition_snapshot(self.model,newer,'standard')['origin'],'preview_mask')
        self.assertEqual(composition_snapshot(self.model,self.template,'magnetic')['origin'],'preview_mask')
