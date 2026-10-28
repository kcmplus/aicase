from io import StringIO
from django.core.management import call_command
from django.test import TestCase
from PIL import Image
from .models import PhoneModel
from .orders import Snapshot
from .phone_templates import PHONE_TEMPLATES, ASSET_ROOT


class PhoneTemplateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_catalog', stdout=StringIO())
        call_command('seed_phone_templates', stdout=StringIO())

    def test_templates_have_correct_dimensions_density_and_camera_transparency(self):
        for t in PHONE_TEMPLATES:
            with Image.open(ASSET_ROOT / t['mask'].lstrip('/')) as image:
                self.assertEqual(image.size, (t['printWidth'], t['printHeight']))
                self.assertAlmostEqual(image.info['dpi'][0], 300, places=2)
                self.assertEqual(image.mode, 'RGBA')
                for x, y in [(0, 0), (.13, .1), (.5, 0), (1, 1)]:
                    self.assertEqual(image.getpixel((int(x*(image.width-1)), int(y*(image.height-1))))[3], 0)
                self.assertEqual(image.getpixel((image.width//2, image.height//2))[3], 255)

    def test_import_preserves_managed_values_and_never_marks_calibrated(self):
        self.assertEqual(PhoneModel.objects.count(), 7)
        self.assertFalse(PhoneModel.objects.filter(code__in=[t['code'] for t in PHONE_TEMPLATES],print_ready=True).exists())
        model=PhoneModel.objects.get(code=PHONE_TEMPLATES[0]['code'])
        model.notes='managed note';model.active=False;model.adaptation_prompt='edited';model.save()
        call_command('seed_phone_templates', stdout=StringIO())
        model.refresh_from_db()
        self.assertEqual(model.notes, 'managed note');self.assertFalse(model.active)
        self.assertEqual(model.adaptation_prompt, 'edited');self.assertEqual(PhoneModel.objects.count(), 7)

    def test_order_validation_pins_template_and_rejects_mismatch_or_inactive_model(self):
        for t in PHONE_TEMPLATES:
            snapshot={'version':2,'code':'POP-C-0123456789ABCDEF','source':'collection','designId':'bloom','model':t['model'],'phoneTemplateId':t['id'],'photo':'','effect':'original','intensity':65,'zoom':100,'x':50,'y':50}
            valid=Snapshot(data=snapshot);self.assertTrue(valid.is_valid(),valid.errors)
            self.assertEqual(valid.validated_data['phoneTemplateId'],t['id'])
            legacy_client=Snapshot(data={k:v for k,v in snapshot.items() if k!='phoneTemplateId'})
            self.assertTrue(legacy_client.is_valid(),legacy_client.errors)
            self.assertEqual(legacy_client.validated_data['phoneTemplateId'],t['id'])
            invalid=Snapshot(data={**snapshot,'phoneTemplateId':'other-template'})
            self.assertFalse(invalid.is_valid())
            PhoneModel.objects.filter(code=t['code']).update(active=False)
            inactive=Snapshot(data=snapshot);self.assertFalse(inactive.is_valid())

    def test_only_supplied_mode_removes_old_models_from_public_catalog_without_deleting(self):
        old_ids=list(PhoneModel.objects.filter(legacy_index__isnull=False).values_list('id', flat=True))
        call_command('seed_phone_templates', only_supplied=True, stdout=StringIO())
        self.assertEqual(set(PhoneModel.objects.filter(active=True).values_list('name', flat=True)), {'iPhone 17', 'iPhone 16e'})
        self.assertEqual(PhoneModel.objects.filter(id__in=old_ids).count(), 5)
        public=self.client.get('/api/v1/catalog/').json()
        self.assertEqual({m['name'] for m in public['phone_models']}, {'iPhone 17', 'iPhone 16e'})
        call_command('seed_phone_templates', only_supplied=True, stdout=StringIO())
        self.assertEqual(PhoneModel.objects.count(), 7)
