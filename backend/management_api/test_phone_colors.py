"""Development regression: synthetic assets, temporary media and Django's isolated test DB."""
import hashlib
import json
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image, ImageDraw
from django.contrib.auth.models import User, Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction, connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from .models import Brand, PhoneModel, PhoneColor, PhoneColorResource, AuditLog
from .phone_templates import PHONE_TEMPLATES
from .phone_colors import MAX_BYTES


class PhoneColorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.template = PHONE_TEMPLATES[0]
        cls.brand = Brand.objects.create(code='synthetic-brand', name='Synthetic')
        cls.model = PhoneModel.objects.create(brand=cls.brand, code=cls.template['code'],
            name=cls.template['model'], preview_family='iphone')
        cls.other = PhoneModel.objects.create(brand=cls.brand, code='other', name='Other', preview_family='iphone')
        cls.admin = User.objects.create_user('synthetic-admin', is_staff=True, is_superuser=True)
        cls.staff = User.objects.create_user('synthetic-staff', is_staff=True)
        cls.base = '/api/v1/admin/phone-colors/'

    def setUp(self):
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.override = override_settings(MEDIA_ROOT=self.media.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        # A regression must never reach a real external image/provider service.
        self.network = patch('requests.sessions.Session.request', side_effect=AssertionError('external network forbidden'))
        self.network.start()
        self.addCleanup(self.network.stop)

    def payload(self, **kwargs):
        return {'phone_model': self.model.pk, 'code': 'natural', 'name': 'Natural',
                'rgb': {'r': 10, 'g': 128, 'b': 255}, **kwargs}

    def create(self, **kwargs):
        response = self.client.post(self.base, self.payload(**kwargs), format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def png(self, size=None, opaque=False, tiny=False):
        size = size or (self.template['sourceWidth'], self.template['sourceHeight'])
        image = Image.new('RGBA', size, (20, 30, 40, 255))
        if not opaque:
            if tiny:
                image.putpixel((0, 0), (0, 0, 0, 0))
            else:
                ImageDraw.Draw(image).rectangle((size[0]//4, size[1]//4, 3*size[0]//4, 3*size[1]//4), fill=(0, 0, 0, 0))
        output = BytesIO()
        image.save(output, format='PNG')
        return output.getvalue()

    def upload(self, color, overlay=None, mask=None, template_id=None):
        return self.client.post(f'{self.base}{color["id"]}/resources/', {
            'overlay': SimpleUploadedFile('overlay.png', overlay if overlay is not None else self.png(), 'image/png'),
            'mask': SimpleUploadedFile('mask.png', mask if mask is not None else self.png(), 'image/png'),
            'template_id': template_id or self.template['id']}, format='multipart')

    def verify(self, color, version=1):
        return self.client.post(f'{self.base}{color["id"]}/verify-resources/',
            {'version': version, 'review_note': '合成图片：核对授权、尺寸与透明范围；非打印校准'}, format='json')

    def enable(self, color):
        return self.client.patch(f'{self.base}{color["id"]}/', {'active': True}, format='json')

    def grant(self, *names):
        self.staff.user_permissions.set(Permission.objects.filter(content_type__app_label='management_api', codename__in=names))
        self.client.force_authenticate(User.objects.get(pk=self.staff.pk))

    def test_draft_persists_rgb_metadata_and_sort_without_resources(self):
        color = self.create(sort_order=7, is_default=True, source='synthetic reference', region_note='region / network')
        self.assertFalse(color['active'])
        self.assertIsNone(color['resource'])
        loaded = self.client.get(f'{self.base}{color["id"]}/').data
        self.assertEqual(loaded['rgb'], {'r': 10, 'g': 128, 'b': 255})
        self.assertEqual(loaded['sort_order'], 7)
        self.assertEqual(loaded['source'], 'synthetic reference')
        self.assertEqual(loaded['region_note'], 'region / network')
        self.assertEqual(AuditLog.objects.filter(resource='management_api.phonecolor', action='create').count(), 1)

    def test_rgb_rejects_missing_extra_bool_string_fraction_and_range(self):
        invalid = [None, [], '#ffffff', {}, {'r': 0, 'g': 0}, {'r': 0, 'g': 0, 'b': 0, 'a': 1}]
        for value in (-1, 256, 1.5, True, False, '20', None):
            for channel in ('r', 'g', 'b'):
                invalid.append({'r': 0, 'g': 0, 'b': 0, channel: value})
        for rgb in invalid:
            with self.subTest(rgb=rgb):
                self.assertEqual(self.client.post(self.base, self.payload(rgb=rgb), format='json').status_code, 400)
        self.assertEqual(PhoneColor.objects.count(), 0)
        self.assertEqual(self.client.post(self.base, {k:v for k,v in self.payload().items() if k!='rgb'}, format='json').status_code, 400)
        self.create(rgb={'r': 0, 'g': 255, 'b': 128})

    def test_rgb_update_rejects_partial_channels_without_modifying_record(self):
        color = self.create()
        self.assertEqual(self.client.patch(f'{self.base}{color["id"]}/', {'rgb': {'r': 1}}, format='json').status_code, 400)
        self.assertEqual(PhoneColor.objects.get(pk=color['id']).rgb, color['rgb'])

    def test_stable_per_model_code_and_single_default(self):
        first = self.create(is_default=True)
        self.assertEqual(self.client.post(self.base, self.payload(), format='json').status_code, 400)
        self.assertEqual(self.client.patch(f'{self.base}{first["id"]}/', {'code': 'changed'}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(f'{self.base}{first["id"]}/', {'phone_model': self.other.pk}, format='json').status_code, 400)
        self.assertEqual(self.client.post(self.base, self.payload(code='second', is_default=True), format='json').status_code, 400)
        second = self.create(code='second')
        self.assertEqual(self.client.patch(f'{self.base}{first["id"]}/', {'is_default': False}, format='json').status_code, 200)
        self.assertEqual(self.client.patch(f'{self.base}{second["id"]}/', {'is_default': True}, format='json').status_code, 200)
        self.create(phone_model=self.other.pk, is_default=True)

    def test_database_constraints_protect_duplicate_code_and_default(self):
        self.create(is_default=True)
        for code, default in [('natural', False), ('second', True)]:
            with self.subTest(code=code), self.assertRaises(IntegrityError), transaction.atomic():
                PhoneColor.objects.create(phone_model=self.model, code=code, rgb={'r':0,'g':0,'b':0}, is_default=default)

    def test_rgb_can_enable_without_resources_but_image_verification_stays_separate(self):
        self.assertEqual(self.client.post(self.base, self.payload(code='active-rgb', active=True), format='json').status_code, 201)
        color = self.create()
        self.assertEqual(self.enable(color).status_code, 200)
        self.assertEqual(self.verify(color).status_code, 400)
        self.assertEqual(self.upload(color).status_code, 200)
        self.assertEqual(self.enable(color).status_code, 200)
        self.assertEqual(self.verify(color).status_code, 200)
        self.assertEqual(self.enable(color).status_code, 200)
        self.assertTrue(PhoneColor.objects.get(pk=color['id']).active)

    def test_resource_replacement_versions_preserve_history_and_invalidate_review(self):
        color = self.create()
        self.assertEqual(self.upload(color).status_code, 200)
        self.assertEqual(self.verify(color).status_code, 200)
        self.assertEqual(self.enable(color).status_code, 200)
        result = self.upload(color)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data['resource']['version'], 2)
        self.assertFalse(result.data['active'])
        self.assertIsNone(result.data['resource']['verified_at'])
        self.assertEqual(self.verify(color, version=1).status_code, 400)
        self.assertEqual(self.enable(color).status_code, 200)
        versions = PhoneColorResource.objects.filter(color_id=color['id']).order_by('version')
        self.assertEqual(versions.count(), 2)
        self.assertIsNotNone(versions[0].verified_at)
        self.assertTrue((Path(self.media.name)/versions[0].overlay).exists())
        self.assertEqual(self.verify(color, version=2).status_code, 200)
        actions = list(AuditLog.objects.filter(resource='management_api.phonecolor').values_list('action', flat=True))
        for action in ('create', 'upload', 'verify', 'update'):
            self.assertIn(action, actions)

    def test_upload_rejects_fake_format_bad_dimensions_and_transparency(self):
        color = self.create()
        invalid = [b'not png', b'<svg/>', self.png((32, 32)), self.png(opaque=True), self.png(tiny=True),
                   self.png((4097, 32)), self.png((3000, 3000)), b'0'*(MAX_BYTES+1)]
        jpg = BytesIO(); Image.new('RGB', (100, 100)).save(jpg, 'JPEG'); invalid.append(jpg.getvalue())
        for image in invalid:
            with self.subTest(size=len(image)):
                result = self.upload(color, overlay=image)
                self.assertEqual(result.status_code, 400, result.data)
        self.assertEqual(self.upload(color, mask=self.png((32, 32))).status_code, 400)
        self.assertEqual(PhoneColorResource.objects.count(), 0)
        self.assertEqual(list(Path(self.media.name).rglob('*.png')), [])

    def test_unknown_template_and_arbitrary_paths_never_become_resources(self):
        color = self.create()
        self.assertEqual(self.upload(color, template_id='unknown').status_code, 400)
        for payload in ({'overlay': '/media/customer.png', 'mask': '/etc/passwd', 'template_id': self.template['id']},
                        {'overlay': 'https://example.invalid/x.png', 'mask': '../x.png', 'template_id': self.template['id']}):
            self.assertEqual(self.client.post(f'{self.base}{color["id"]}/resources/', payload, format='json').status_code, 400)
        for field, value in [('current_resource', 1), ('resource', {}), ('overlay', '/media/x.png'), ('verified_at', 'now')]:
            self.assertEqual(self.client.patch(f'{self.base}{color["id"]}/', {field: value}, format='json').status_code, 400)
        self.assertEqual(PhoneColorResource.objects.count(), 0)

    def test_corrupt_missing_and_wrong_model_resources_cannot_verify_but_allow_rgb(self):
        color = self.create()
        for mode in ('corrupt', 'missing', 'path', 'wrong-template'):
            self.assertEqual(self.upload(color).status_code, 200)
            resource = PhoneColor.objects.get(pk=color['id']).current_resource
            self.assertEqual(self.verify(color, resource.version).status_code, 200)
            if mode == 'corrupt':
                (Path(self.media.name)/resource.overlay).write_bytes(b'corrupt')
            elif mode == 'missing':
                (Path(self.media.name)/resource.overlay).unlink()
            elif mode == 'path':
                resource.overlay = '../private.png'; resource.save()
            else:
                resource.template_id = 'other-template'; resource.save()
            self.assertEqual(self.verify(color, resource.version).status_code, 400)
            self.assertEqual(self.enable(color).status_code, 200)

    def test_resource_cannot_be_reused_by_another_color_even_if_manually_referenced(self):
        first, second = self.create(), self.create(code='second')
        self.assertEqual(self.upload(first).status_code, 200)
        self.assertEqual(self.verify(first).status_code, 200)
        resource = PhoneColor.objects.get(pk=first['id']).current_resource
        PhoneColor.objects.filter(pk=second['id']).update(current_resource=resource)
        self.assertEqual(self.enable(second).status_code, 200)

    def test_revalidate_decode_even_when_hash_was_replaced(self):
        color = self.create(); self.assertEqual(self.upload(color).status_code, 200)
        resource = PhoneColor.objects.get(pk=color['id']).current_resource
        data = self.png(opaque=True)
        (Path(self.media.name)/resource.overlay).write_bytes(data)
        resource.overlay_sha256 = hashlib.sha256(data).hexdigest(); resource.save()
        self.assertEqual(self.verify(color).status_code, 400)

    def test_review_requires_exact_version_and_nonempty_note(self):
        color = self.create(); self.assertEqual(self.upload(color).status_code, 200)
        for body in ({}, {'version': True, 'review_note':'x'}, {'version': '1', 'review_note':'x'},
                     {'version':1, 'review_note':''}, {'version':1, 'review_note':'x'*501},
                     {'version':1, 'review_note':'x', 'active':True}):
            self.assertEqual(self.client.post(f'{self.base}{color["id"]}/verify-resources/', body, format='json').status_code, 400)

    def test_color_permissions_are_independent_from_phone_model_permissions(self):
        color = self.create()
        self.grant('view_phonemodel', 'change_phonemodel')
        self.assertEqual(self.client.get(self.base).status_code, 403)
        self.assertEqual(self.upload(color).status_code, 403)
        self.grant('view_phonecolor')
        self.assertEqual(self.client.get(self.base).status_code, 200)
        self.assertEqual(self.client.get(self.base+'options_catalog/').status_code, 200)
        self.assertEqual(self.client.post(self.base, self.payload(code='second'), format='json').status_code, 403)
        self.assertEqual(self.enable(color).status_code, 403)
        self.grant('view_phonecolor', 'add_phonecolor')
        self.create(code='second')
        self.grant('view_phonecolor', 'change_phonecolor')
        self.assertEqual(self.upload(color).status_code, 200)
        self.assertEqual(self.verify(color).status_code, 403)
        self.grant('view_phonecolor', 'change_phonecolor', 'verify_phonecolor')
        self.assertEqual(self.verify(color).status_code, 200)
        self.assertEqual(self.enable(color).status_code, 200)
        self.assertEqual(self.client.delete(f'{self.base}{color["id"]}/').status_code, 403)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.delete(f'{self.base}{color["id"]}/').status_code, 405)
        self.assertTrue(PhoneColor.objects.filter(pk=color['id']).exists())

    def test_session_csrf_required_for_create_patch_upload_and_verify(self):
        color = self.create()
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.post(self.base, self.payload(code='csrf'), format='json').status_code, 403)
        self.assertEqual(client.patch(f'{self.base}{color["id"]}/', {'name':'changed'}, format='json').status_code, 403)
        for action in ('resources', 'verify-resources'):
            self.assertEqual(client.post(f'{self.base}{color["id"]}/{action}/', {}, format='json').status_code, 403)
        token = client.get('/api/v1/auth/csrf/').data['csrfToken']
        self.assertEqual(client.post(self.base, self.payload(code='csrf'), format='json', HTTP_X_CSRFTOKEN=token).status_code, 201)

    def test_anonymous_and_non_staff_never_access_configuration(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.base).status_code, 403)
        nonstaff = User.objects.create_user('nonstaff', is_superuser=True)
        self.client.force_authenticate(nonstaff)
        self.assertEqual(self.client.get(self.base).status_code, 403)

    def test_admin_template_options_and_filter_do_not_change_model_or_inventory(self):
        color = self.create()
        options = self.client.get(self.base+'options_catalog/').data
        item = next(item for item in options if item['id'] == self.model.pk)
        self.assertEqual(item['templates'][0]['id'], self.template['id'])
        self.assertEqual(self.client.get(f'{self.base}?phone_model={self.other.pk}').data['count'], 0)
        self.assertEqual(self.client.get(f'{self.base}?phone_model={self.model.pk}').data['results'][0]['id'], color['id'])
        self.assertEqual(self.client.get(f'{self.base}?phone_model=bad').status_code, 400)
        self.model.refresh_from_db()
        self.assertFalse(self.model.print_ready)
        self.assertEqual(self.client.get('/api/v1/store/phone-models/', {'device_id': '401', 'shop_id': '146'}).data['models'], [])

    def test_out_of_range_model_filter_returns_validation_error(self):
        response = self.client.get(self.base, {'phone_model': '999999999999999999999999999999'})
        self.assertEqual(response.status_code, 400)

    def test_model_filter_rejects_invalid_id_boundaries_for_view_only_staff(self):
        self.grant('view_phonecolor')
        for value in (str(2**63), '9' * 5000, '0', '-1', '1.0', '+1', '１', ''):
            with self.subTest(value=value[:30]):
                response = self.client.get(self.base, {'phone_model': value})
                self.assertEqual(response.status_code, 400, response.data)
                self.assertTrue(response.data)
                self.assertIn('机型参数', str(response.data))

    def test_model_filter_accepts_bigint_limit_and_preserves_exact_selection(self):
        color = self.create()
        other_color = self.create(phone_model=self.other.pk)
        self.grant('view_phonecolor')
        for value in (str(self.model.pk), f'00{self.model.pk}'):
            with self.subTest(value=value):
                response = self.client.get(self.base, {'phone_model': value})
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual([item['id'] for item in response.data['results']], [color['id']])
        response = self.client.get(self.base, {'phone_model': str(2**63 - 1)})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['count'], 0)
        self.assertEqual(PhoneColor.objects.count(), 2)
        self.assertEqual(PhoneColor.objects.get(pk=other_color['id']).phone_model_id, self.other.pk)

    def test_supplier_template_replacement_invalidates_resource_verification(self):
        from django.utils import timezone
        from .models import DeviceProviderConnection, Device, SupplierProduct, DeviceProduct
        from .store_catalog import stock_template
        connection = DeviceProviderConnection.objects.create(name='Synthetic', shop_id='999', base_url='https://example.invalid')
        device = Device.objects.create(connection=connection, vendor_device_id='999', name='Synthetic')
        product = SupplierProduct.objects.create(connection=connection, goods_id='1', product_id='1', name='Synthetic', phone_model=self.other)
        stock = DeviceProduct.objects.create(device=device, product=product, observed_at=timezone.now(),
            template_url='https://example.invalid/template.png', template_imported_url='https://example.invalid/template.png',
            template_image='synthetic-original.png', template_mask='synthetic-mask.png', template_width=128, template_height=256)
        template_id = stock_template(stock)['id']
        color = self.create(phone_model=self.other.pk)
        wrong = self.create(code='wrong-model')
        self.assertEqual(self.upload(wrong, template_id=template_id).status_code, 400)
        self.assertEqual(self.upload(color, overlay=self.png((128,256)), mask=self.png((128,256)), template_id=template_id).status_code, 200)
        self.assertEqual(self.verify(color).status_code, 200)
        self.assertEqual(self.enable(color).status_code, 200)
        stock.template_image = 'synthetic-replacement.png'; stock.save()
        self.assertEqual(self.enable(color).status_code, 200)
        self.assertEqual(self.verify(color).status_code, 400)


class PhoneColorInitializationTests(TestCase):
    """Run the actual checked-in reference against new synthetic model rows."""
    @classmethod
    def setUpTestData(cls):
        from .phone_color_initialization import REFERENCE_PATH
        cls.raw_reference = REFERENCE_PATH.read_bytes()
        cls.reference = json.loads(cls.raw_reference)
        cls.admin = User.objects.create_user('initialization-admin', is_staff=True, is_superuser=True)
        cls.staff = User.objects.create_user('initialization-staff', is_staff=True)
        cls.url = '/api/v1/admin/phone-colors/initialize-reference/'

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        network = patch('requests.sessions.Session.request', side_effect=AssertionError('external network forbidden'))
        network.start()
        self.addCleanup(network.stop)

    def populate(self):
        brands = {}
        for index, entry in enumerate(self.reference['models']):
            brand = brands.get(entry['brand'])
            if brand is None:
                brand = Brand.objects.create(name=entry['brand'], code=f'synthetic-brand-{index}')
                brands[entry['brand']] = brand
            PhoneModel.objects.create(brand=brand, code=f'synthetic-model-{index}',
                name=entry['model_name'], preview_family='iphone', active=False, notes='manual model notes')

    def preview(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def execute(self, preview=None):
        response = self.client.post(self.url, {'reference_sha256': (preview or self.preview())['reference_sha256'],
                                              'confirm': True}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_preview_uses_all_50_reference_models_and_218_colors_without_writes(self):
        self.populate()  # Include even the six unverified models to prove they are skipped.
        models_before = list(PhoneModel.objects.values())
        preview = self.preview()
        self.assertEqual(preview['mode'], 'preview')
        self.assertEqual(preview['reference_sha256'], hashlib.sha256(self.raw_reference).hexdigest())
        self.assertEqual(preview['summary'], dict(total_models=50, verified_models=44, reference_colors=218,
            matched_models=44, unmatched_models=0, ambiguous_models=0, needs_review_models=6,
            new_colors=218, existing_colors=0))
        self.assertEqual(len(preview['items']), 50)
        for item in preview['items']:
            if item['match_status'] == 'needs_review':
                self.assertEqual(item['result'], 'needs_review')
                self.assertIsNone(item['phone_model'])
                self.assertEqual(item['colors'], [])
            else:
                self.assertEqual(item['result'], 'matched')
                self.assertTrue(all(c['result'] == 'would_create' and c['id'] is None for c in item['colors']))
        self.assertEqual(PhoneColor.objects.count(), 0)
        self.assertEqual(AuditLog.objects.count(), 0)
        self.assertEqual(list(PhoneModel.objects.values()), models_before)

    def test_two_executions_are_idempotent_and_preserve_every_manual_field_and_model(self):
        self.populate()
        models_before = list(PhoneModel.objects.values())
        first = self.execute()
        self.assertEqual(first['mode'], 'executed')
        self.assertEqual(first['summary']['new_colors'], 218)
        self.assertEqual(first['summary']['existing_colors'], 0)
        self.assertEqual(PhoneColor.objects.count(), 218)
        self.assertFalse(PhoneColor.objects.filter(active=True).exists())
        self.assertFalse(PhoneColor.objects.filter(is_default=True).exists())
        self.assertFalse(PhoneColor.objects.filter(current_resource__isnull=False).exists())
        self.assertEqual(PhoneColorResource.objects.count(), 0)
        self.assertEqual(AuditLog.objects.filter(action='initialize').count(), 219)
        color = PhoneColor.objects.first()
        # Represent an already configured historical preview; initialization must
        # never validate, replace, disable, or otherwise modify existing records.
        resource = PhoneColorResource.objects.create(color=color, version=7, template_id='synthetic-version',
            width=100, height=200, overlay='synthetic-overlay', mask='synthetic-mask',
            overlay_sha256='a'*64, mask_sha256='b'*64, uploaded_by='manual')
        color.rgb = {'r': 1, 'g': 2, 'b': 3}
        color.name = '人工修改'
        color.source = 'manual source'
        color.region_note = 'manual special edition'
        color.sort_order = 999
        color.is_default = color.active = True
        color.current_resource = resource
        color.save()
        colors_before = list(PhoneColor.objects.values())
        resources_before = list(PhoneColorResource.objects.values())
        second = self.execute(first)
        self.assertEqual(second['summary']['new_colors'], 0)
        self.assertEqual(second['summary']['existing_colors'], 218)
        self.assertEqual(list(PhoneColor.objects.values()), colors_before)
        self.assertEqual(list(PhoneColorResource.objects.values()), resources_before)
        self.assertEqual(list(PhoneModel.objects.values()), models_before)
        self.assertTrue(all(c['result'] == 'existing' for item in second['items'] for c in item['colors']))
        log = AuditLog.objects.filter(action='initialize').order_by('-id').first()
        self.assertIn(second['reference_sha256'], log.summary)
        self.assertIn('新增 0，已有 218', log.summary)
        self.assertEqual(log.actor_id, self.admin.pk)

    def test_exact_brand_and_name_only_ambiguities_and_unknown_models_are_skipped(self):
        apple = Brand.objects.create(name='Apple', code='apple')
        other = Brand.objects.create(name='Other', code='other')
        for index, (brand, name) in enumerate([(apple, 'iPhone 13 Pro'), (apple, 'iPhone 13 Pro'),
                (apple, 'iPhone 17 Pro'), (other, 'iPhone 17 Pro Max'), (apple, 'iphone 17 Pro Max'),
                (apple, 'iPhone 11 Pro '), (apple, 'Samsung A56')]):
            PhoneModel.objects.create(brand=brand, name=name, code=f'mixed-{index}', preview_family='iphone')
        result = self.execute()
        self.assertEqual(result['summary']['matched_models'], 1)
        self.assertEqual(result['summary']['ambiguous_models'], 1)
        self.assertEqual(result['summary']['unmatched_models'], 42)
        self.assertEqual(result['summary']['needs_review_models'], 6)
        self.assertEqual(result['summary']['new_colors'], 3)
        self.assertEqual(PhoneModel.objects.count(), 7)
        self.assertEqual(set(PhoneColor.objects.values_list('phone_model__name', flat=True)), {'iPhone 17 Pro'})
        self.assertEqual(len(result['items'][0]['candidate_ids']), 2)

    def test_imported_values_and_special_edition_notes_remain_exactly_from_reference(self):
        self.populate()
        result = self.execute()
        for entry, item in zip(self.reference['models'], result['items']):
            for index, (source, row) in enumerate(zip(entry['colors'], item['colors'])):
                color = PhoneColor.objects.get(pk=row['id'])
                self.assertEqual(color.rgb, source['rgb'])
                self.assertEqual(color.code, source['code'])
                self.assertEqual(color.name, f"{source['name_zh']} / {source['name_en']}")
                self.assertEqual(color.sort_order, index)
                self.assertEqual(color.region_note, '；'.join(entry.get(k, '') for k in ('market', 'connectivity', 'notes')))
                for source in entry['sources']:
                    self.assertIn(source['url'], color.source)
                self.assertFalse(color.active)

    def test_execution_recomputes_current_matches_and_preserves_intervening_manual_add(self):
        empty_preview = self.preview()
        self.assertEqual(empty_preview['summary']['new_colors'], 0)
        self.populate()
        model = PhoneModel.objects.get(name='iPhone 13 Pro')
        existing = PhoneColor.objects.create(phone_model=model, code='graphite', rgb={'r': 0, 'g': 0, 'b': 0},
                                              source='manual', is_default=True)
        before = PhoneColor.objects.filter(pk=existing.pk).values().get()
        result = self.execute(empty_preview)
        self.assertEqual(result['summary']['new_colors'], 217)
        self.assertEqual(result['summary']['existing_colors'], 1)
        self.assertEqual(PhoneColor.objects.filter(pk=existing.pk).values().get(), before)

    def test_execution_rejects_stale_reference_and_all_caller_supplied_data(self):
        self.populate()
        digest = self.preview()['reference_sha256']
        for payload in ({}, {'confirm': True, 'reference_sha256': '0'*64},
                {'confirm': 'true', 'reference_sha256': digest}, {'confirm': 1, 'reference_sha256': digest},
                {'confirm': False, 'reference_sha256': digest}, {'confirm': True, 'reference_sha256': None},
                {'confirm': True, 'reference_sha256': digest, 'path': '/tmp/other.json'},
                {'confirm': True, 'reference_sha256': digest, 'colors': []}):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post(self.url, payload, format='json').status_code, 400)
        self.assertEqual(PhoneColor.objects.count(), 0)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_changed_reference_requires_new_preview_and_invalid_rgb_never_partially_imports(self):
        self.populate()
        digest = self.preview()['reference_sha256']
        with TemporaryDirectory() as temporary:
            source = Path(temporary) / 'reference.json'
            source.write_bytes(self.raw_reference + b'\n')
            with patch('management_api.phone_color_initialization.REFERENCE_PATH', source):
                response = self.client.post(self.url, {'confirm':True,'reference_sha256':digest}, format='json')
                self.assertEqual(response.status_code, 400)
                self.assertIn('重新预览', str(response.data))
                self.assertNotEqual(self.preview()['reference_sha256'], digest)
            invalid = json.loads(self.raw_reference)
            invalid['models'][1]['colors'][0]['rgb']['r'] = True
            source.write_text(json.dumps(invalid))
            with patch('management_api.phone_color_initialization.REFERENCE_PATH', source):
                digest = hashlib.sha256(source.read_bytes()).hexdigest()
                response = self.client.post(self.url, {'confirm':True,'reference_sha256':digest}, format='json')
                self.assertEqual(response.status_code, 400)
                self.assertIn('RGB', str(response.data))
        self.assertEqual(PhoneColor.objects.count(), 0)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_initialization_requires_independent_color_view_and_add_permissions(self):
        digest = hashlib.sha256(self.raw_reference).hexdigest()
        for permissions, get_status, post_status in [([],403,403), (['view_phonecolor'],200,403),
                (['add_phonecolor'],403,403), (['view_phonemodel','change_phonemodel'],403,403),
                (['view_phonecolor','add_phonecolor'],200,200)]:
            with self.subTest(permissions=permissions):
                self.staff.user_permissions.set(Permission.objects.filter(codename__in=permissions))
                self.client.force_authenticate(User.objects.get(pk=self.staff.pk))
                self.assertEqual(self.client.get(self.url).status_code, get_status)
                self.assertEqual(self.client.post(self.url, {'reference_sha256':digest,'confirm':True}, format='json').status_code, post_status)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, {'reference_sha256':digest,'confirm':True}, format='json').status_code, 403)

    def test_session_initialization_requires_csrf(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.admin)
        preview = client.get(self.url)
        self.assertEqual(preview.status_code, 200)
        payload = {'reference_sha256': preview.data['reference_sha256'], 'confirm': True}
        self.assertEqual(client.post(self.url, payload, format='json').status_code, 403)
        token = client.get('/api/v1/auth/csrf/').data['csrfToken']
        self.assertEqual(client.post(self.url, payload, format='json', HTTP_X_CSRFTOKEN=token).status_code, 200)

    def test_audit_failure_rolls_back_entire_import_and_does_not_leave_partial_colors(self):
        self.populate()
        preview = self.preview()
        with patch('management_api.phone_color_initialization.audit', side_effect=RuntimeError('synthetic audit failure')):
            with self.assertRaisesRegex(RuntimeError, 'synthetic audit failure'):
                self.execute(preview)
        self.assertEqual(PhoneColor.objects.count(), 0)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_summary_audit_failure_rolls_back_all_prior_color_writes(self):
        from .audit import audit as real_audit
        self.populate()
        preview = self.preview()
        calls = []

        def fail_summary(*args, **kwargs):
            calls.append(1)
            if 'summary' in kwargs:
                raise RuntimeError('synthetic summary audit failure')
            return real_audit(*args, **kwargs)

        with patch('management_api.phone_color_initialization.audit', side_effect=fail_summary):
            with self.assertRaisesRegex(RuntimeError, 'synthetic summary audit failure'):
                self.execute(preview)
        self.assertEqual(len(calls), 219)
        self.assertEqual(PhoneColor.objects.count(), 0)
        self.assertEqual(AuditLog.objects.count(), 0)


class PhoneColorMigrationTests(TransactionTestCase):
    def test_additive_migration_preserves_historical_models_and_order_snapshots(self):
        before = [('management_api', '0033_merge_catalog_location'), ('management_api', '0033_order_case_material'), ('management_api', '0031_direct_debug_transport')]
        after = MigrationExecutor(connection).loader.graph.leaf_nodes('management_api')
        executor = MigrationExecutor(connection)
        executor.migrate(before)
        try:
            apps = executor.loader.project_state(before).apps
            brand = apps.get_model('management_api', 'Brand').objects.create(code='historical', name='Historical')
            model = apps.get_model('management_api', 'PhoneModel').objects.create(brand=brand, code='historical',
                name='Historical', preview_family='iphone', notes='manual configuration', active=False)
            order = apps.get_model('management_api', 'PrintOrder').objects.create(model_name='Historical',
                amount='29.70', status='paid', mode='airwallex_live', snapshot={'quantity':3, 'image':'synthetic'}, revision=7)
            model.refresh_from_db()
            order.refresh_from_db()
            expected_model = {f.attname: getattr(model, f.attname) for f in model._meta.fields}
            expected_order = {f.attname: getattr(order, f.attname) for f in order._meta.fields}
            executor = MigrationExecutor(connection)
            executor.migrate(after)
            apps = executor.loader.project_state(after).apps
            model = apps.get_model('management_api', 'PhoneModel').objects.get(pk=model.pk)
            order = apps.get_model('management_api', 'PrintOrder').objects.get(pk=order.pk)
            self.assertEqual({f.attname: getattr(model, f.attname) for f in model._meta.fields}, expected_model)
            self.assertEqual({key: getattr(order, key) for key in expected_order}, expected_order)
            self.assertEqual(order.delivery_address, {})
            self.assertEqual(order.shipping_quote, {})
            self.assertEqual(apps.get_model('management_api', 'PhoneColor').objects.count(), 0)
        finally:
            MigrationExecutor(connection).migrate(after)
