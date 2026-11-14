"""Development regression: synthetic assets, temporary media and Django's isolated test DB."""
import hashlib
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

    def test_draft_cannot_enable_without_uploaded_verified_resources(self):
        self.assertEqual(self.client.post(self.base, self.payload(active=True), format='json').status_code, 400)
        color = self.create()
        self.assertEqual(self.enable(color).status_code, 400)
        self.assertEqual(self.verify(color).status_code, 400)
        self.assertEqual(self.upload(color).status_code, 200)
        self.assertEqual(self.enable(color).status_code, 400)
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
        self.assertEqual(self.enable(color).status_code, 400)
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

    def test_corrupt_missing_and_wrong_model_resources_cannot_verify_or_enable(self):
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
            self.assertEqual(self.enable(color).status_code, 400)

    def test_resource_cannot_be_reused_by_another_color_even_if_manually_referenced(self):
        first, second = self.create(), self.create(code='second')
        self.assertEqual(self.upload(first).status_code, 200)
        self.assertEqual(self.verify(first).status_code, 200)
        resource = PhoneColor.objects.get(pk=first['id']).current_resource
        PhoneColor.objects.filter(pk=second['id']).update(current_resource=resource)
        self.assertEqual(self.enable(second).status_code, 400)

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
        self.assertEqual(self.client.get('/api/v1/store/phone-models/').data['models'], [])

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

    def test_supplier_template_is_bound_to_model_and_replacement_invalidates_activation(self):
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
        self.assertEqual(self.enable(color).status_code, 400)
        self.assertEqual(self.verify(color).status_code, 400)


class PhoneColorMigrationTests(TransactionTestCase):
    def test_additive_migration_preserves_historical_models_and_order_snapshots(self):
        before = [('management_api', '0033_merge_catalog_location')]
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
            self.assertEqual({f.attname: getattr(order, f.attname) for f in order._meta.fields}, expected_order)
            self.assertEqual(apps.get_model('management_api', 'PhoneColor').objects.count(), 0)
        finally:
            MigrationExecutor(connection).migrate(after)
