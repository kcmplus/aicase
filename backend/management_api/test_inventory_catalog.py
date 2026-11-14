from django.contrib.auth.models import User, Permission
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .inventory_catalog import sync_models
from .inventory import CATALOG_SYNC_PERMISSIONS
from .models import Brand, PhoneModel, SupplierProduct, DeviceProduct, Device, DeviceProviderConnection, AuditLog


class InventoryCatalogTests(TestCase):
    def setUp(self):
        self.connection = DeviceProviderConnection.objects.create(name='Test', base_url='https://shop.widermatrix.cn', shop_id='146')
        self.device = Device.objects.create(connection=self.connection, vendor_device_id='401', name='Test')
        self.apple = Brand.objects.create(code='apple', name='Apple')
        PhoneModel.objects.create(code='model-1', name='iPhone 16 Pro', brand=self.apple,
                                  preview_family='iphone', legacy_index=1, active=False)
        for suffix in ('', ' Pro'):
            PhoneModel.objects.create(code='seed-15'+suffix.replace(' ', '-').lower(), name='iPhone 15'+suffix,
                                      brand=self.apple, preview_family='iphone', active=False)

    def product(self, spec='17 Pro', name='iPhone 17', brand='iPhone', device=None, **kwargs):
        device = device or self.device
        p = SupplierProduct.objects.create(connection=device.connection, goods_id=str(SupplierProduct.objects.count()+100),
            product_id='1', name=name, brand_name=brand, specs=[{'spec_name': '型号', 'spec_value': spec}], **kwargs)
        DeviceProduct.objects.create(device=device, product=p, stock=5, observed_at=timezone.now(),
                                     template_url='https://example.com/vendor-template.png')
        return p

    def test_exact_specs_override_family_name_and_clean_invisible_characters(self):
        pro = self.product(spec=' 15 pro\u200b', name='iPhone 15')
        ordinary = self.product(spec='15', name='iPhone 15')
        before = PhoneModel.objects.count()
        result = sync_models(self.device)
        pro.refresh_from_db(); ordinary.refresh_from_db()
        self.assertEqual(result['matched'], 2)
        self.assertEqual(PhoneModel.objects.count(), before)
        self.assertEqual(pro.phone_model.name, 'iPhone 15 Pro')
        self.assertEqual(ordinary.phone_model.name, 'iPhone 15')
        self.assertFalse(pro.phone_model.active)

    def test_new_model_variants_share_identity_without_publishing(self):
        first = self.product()
        second = self.product()
        second.specs.append({'spec_name': '版本', 'spec_value': '磁吸款'}); second.save()
        result = sync_models(self.device)
        first.refresh_from_db(); second.refresh_from_db()
        self.assertEqual((result['created'], result['matched']), (1, 1))
        self.assertEqual(first.phone_model_id, second.phone_model_id)
        self.assertFalse(first.phone_model.active)
        self.assertFalse(first.phone_model.print_ready)
        self.assertIsNone(first.phone_model.legacy_index)
        self.assertFalse(first.active)
        self.assertEqual(first.device_products.get().template_url, 'https://example.com/vendor-template.png')
        self.assertEqual(sync_models(self.device)['preserved'], 2)

    def test_existing_manual_mapping_and_catalog_settings_are_preserved(self):
        model = PhoneModel.objects.get(code='model-1')
        model.print_ready = True; model.notes = 'Keep calibration'; model.save()
        p = self.product(phone_model=model, display_name='My display', active=True)
        result = sync_models(self.device)
        p.refresh_from_db(); model.refresh_from_db()
        self.assertEqual(result['preserved'], 1)
        self.assertEqual((p.phone_model_id, p.display_name, p.active), (model.pk, 'My display', True))
        self.assertEqual((model.print_ready, model.notes, model.legacy_index), (True, 'Keep calibration', 1))

    def test_plus_radio_generation_and_redmi_remain_distinct(self):
        regular = self.product(spec='S24', name='Samsung S24', brand='Samsung')
        plus = self.product(spec='S24+', name='Samsung S24', brand='Samsung')
        redmi4 = self.product(spec='13-4G', name='Redmi 13', brand='Xiaomi')
        redmi5 = self.product(spec='13-5G', name='Redmi 13', brand='Xiaomi')
        xiaomi = self.product(spec='13', name='Xiaomi 13', brand='Xiaomi')
        self.assertEqual(sync_models(self.device)['skipped'], 0)
        models = []
        for p in (regular, plus, redmi4, redmi5, xiaomi):
            p.refresh_from_db(); models.append(p.phone_model_id)
        self.assertEqual(len(set(models)), 5)
        self.assertEqual(redmi4.phone_model.name, 'Redmi 13-4G')
        self.assertFalse(redmi4.phone_model.brand.active)

    def test_ambiguous_or_missing_identity_is_reported_without_guessing(self):
        self.product(spec='')
        self.product(brand='Unknown')
        self.product(spec='13', name='Unknown series', brand='Xiaomi')
        self.product(spec='Xiaomi 13', name='Redmi 13', brand='Xiaomi')
        self.product(spec='15')
        PhoneModel.objects.create(code='duplicate-15', name='iPhone15', brand=self.apple, preview_family='iphone')
        result = sync_models(self.device)
        self.assertEqual(result['skipped'], 5)
        self.assertEqual(len(result['items']), 5)
        self.assertFalse(SupplierProduct.objects.filter(phone_model__isnull=False).exists())

    def test_device_scope_excludes_other_devices_and_removed_goods(self):
        included = self.product()
        removed = self.product(spec='14')
        removed.device_products.update(present=False)
        other = Device.objects.create(connection=self.connection, vendor_device_id='402', name='Other')
        excluded = self.product(spec='13', device=other)
        result = sync_models(self.device)
        self.assertEqual(len(result['items']), 1)
        included.refresh_from_db(); removed.refresh_from_db(); excluded.refresh_from_db()
        self.assertIsNotNone(included.phone_model_id)
        self.assertIsNone(removed.phone_model_id)
        self.assertIsNone(excluded.phone_model_id)

    def test_endpoint_permissions_validation_and_audit(self):
        p = self.product()
        user = User.objects.create_user('catalog-operator', is_staff=True)
        client = APIClient(); client.force_authenticate(user)
        url = '/api/v1/admin/inventory/products/sync-models/'
        for perm in CATALOG_SYNC_PERMISSIONS:
            self.assertEqual(client.post(url, {'device': self.device.pk}, format='json').status_code, 403)
            user.user_permissions.add(Permission.objects.get(codename=perm.split('.')[1]))
            user = User.objects.get(pk=user.pk); client.force_authenticate(user)
        self.assertEqual(client.post(url, {}, format='json').status_code, 400)
        self.assertEqual(client.post(url, {'device': 999999}, format='json').status_code, 400)
        self.assertEqual(client.post(url, {'device': self.device.pk, 'active': True}, format='json').status_code, 400)
        response = client.post(url, {'device': self.device.pk}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['created'], 1)
        self.assertTrue(AuditLog.objects.filter(resource='management_api.supplierproduct', object_id=str(p.pk), actor=user).exists())
        csrf_client = APIClient(enforce_csrf_checks=True); csrf_client.force_login(user)
        self.assertEqual(csrf_client.post(url, {'device': self.device.pk}, format='json').status_code, 403)
