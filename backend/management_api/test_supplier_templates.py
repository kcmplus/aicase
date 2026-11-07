import tempfile
from io import BytesIO
from unittest.mock import patch, MagicMock

from PIL import Image, ImageDraw
from django.contrib.auth.models import User, Permission
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Brand, PhoneModel, DeviceProviderConnection, Device, SupplierProduct, DeviceProduct, AuditLog
from .supplier_templates import import_template, template_info, preview_mask, download_template, TemplateError


def png(closed=True, opaque=False):
    image = Image.new('RGBA', (64, 128), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if closed:
        draw.rectangle((2, 2, 61, 125), outline='black', width=3)
        draw.rectangle((5, 5, 20, 35), fill='black')  # camera exclusion
    if opaque:
        draw.rectangle((0, 0, 63, 127), fill='white')
    output = BytesIO(); image.save(output, format='PNG', dpi=(200, 200))
    return output.getvalue()


class SupplierTemplateTests(TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.override = override_settings(MEDIA_ROOT=self.folder.name)
        self.override.enable(); self.addCleanup(self.override.disable)
        brand = Brand.objects.create(code='test-brand', name='Apple')
        self.model = PhoneModel.objects.create(code='test-model', name='iPhone 17', brand=brand, preview_family='iphone')
        self.connection = DeviceProviderConnection.objects.create(name='Test', base_url='https://shop.widermatrix.cn', shop_id='146')
        self.device = Device.objects.create(connection=self.connection, vendor_device_id='401', name='Test device')
        self.product = SupplierProduct.objects.create(connection=self.connection, goods_id='136', product_id='1', phone_model=self.model)
        self.stock = DeviceProduct.objects.create(device=self.device, product=self.product, observed_at=timezone.now(),
            template_url='http://oss.widermatrix.cn/template.png')

    def do_import(self, data=None, refresh=False):
        with patch('management_api.supplier_templates.download_template', return_value=data or png()) as fetch:
            result = import_template(self.stock.pk, self.model.pk, refresh=refresh)
        return result, fetch

    def test_original_pixels_density_and_mask_are_preserved_without_print_approval(self):
        data = png()
        stock, _ = self.do_import(data)
        self.assertEqual((stock.template_width, stock.template_height), (64, 128))
        with default_storage.open(stock.template_image, 'rb') as source:
            self.assertEqual(source.read(), data)
        with default_storage.open(stock.template_mask, 'rb') as source:
            mask = Image.open(source).convert('RGBA').getchannel('A')
            self.assertEqual(mask.getpixel((32, 64)), 255)
            self.assertEqual(mask.getpixel((10, 10)), 0)
            self.assertEqual(mask.getpixel((0, 0)), 0)
        self.model.refresh_from_db()
        self.assertFalse(self.model.print_ready)
        self.assertEqual(template_info(stock)['status'], 'imported')
        again, fetch = self.do_import()
        fetch.assert_not_called()
        self.assertEqual(stock.template_image, again.template_image)

    def test_opaque_or_open_template_keeps_overlay_but_never_invents_mask(self):
        for data in (png(closed=False), png(opaque=True)):
            stock, _ = self.do_import(data, refresh=True)
            self.assertTrue(stock.template_image)
            self.assertFalse(stock.template_mask)
            self.assertIn('独立遮罩', stock.template_mask_note)

    def test_failed_refresh_preserves_existing_assets(self):
        old, _ = self.do_import()
        with patch('management_api.supplier_templates.download_template', side_effect=TemplateError('下载失败')):
            with self.assertRaises(TemplateError):
                import_template(self.stock.pk, self.model.pk, refresh=True)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.template_image, old.template_image)
        self.assertEqual(template_info(self.stock)['status'], 'imported')
        self.assertEqual(self.stock.template_import_error, '下载失败')

    def test_changed_source_hides_stale_assets_and_rejects_inflight_result(self):
        self.do_import()
        self.stock.template_url = 'https://oss.widermatrix.cn/new.png'; self.stock.save(update_fields=['template_url'])
        self.stock.refresh_from_db()
        self.assertEqual(template_info(self.stock)['image'], '')
        def changing_source(_):
            DeviceProduct.objects.filter(pk=self.stock.pk).update(template_url='https://oss.widermatrix.cn/newer.png')
            return png()
        with patch('management_api.supplier_templates.download_template', side_effect=changing_source):
            with self.assertRaisesMessage(TemplateError, '来源或机型映射已变化'):
                import_template(self.stock.pk, self.model.pk)

    def test_remapping_during_import_cannot_publish_wrong_model(self):
        def remap(_):
            SupplierProduct.objects.filter(pk=self.product.pk).update(phone_model=None)
            return png()
        with patch('management_api.supplier_templates.download_template', side_effect=remap):
            with self.assertRaisesMessage(TemplateError, '来源或机型映射已变化'):
                import_template(self.stock.pk, self.model.pk)
        self.stock.refresh_from_db(); self.assertFalse(self.stock.template_image)

    def test_invalid_images_do_not_publish(self):
        large = Image.new('1', (4097, 32)); output = BytesIO(); large.save(output, format='PNG')
        for data in (b'<html>error</html>', output.getvalue()):
            with self.assertRaises(TemplateError):
                self.do_import(data)
            self.stock.refresh_from_db(); self.assertFalse(self.stock.template_image)

    def test_download_only_trusted_https_without_redirects_or_credentials(self):
        for url in ('https://file.autovendpro.com.evil.com/a.png', 'http://127.0.0.1/a.png', 'https://oss.widermatrix.cn.evil.com/a.png',
                    'https://u:p@oss.widermatrix.cn/a.png', 'https://oss.widermatrix.cn:444/a.png'):
            with patch('management_api.supplier_templates.requests.get') as get:
                with self.assertRaises(TemplateError): download_template(url)
                get.assert_not_called()
        response = MagicMock(); response.__enter__.return_value = response
        response.status_code = 200; response.iter_content.return_value = [png()]
        with patch('management_api.supplier_templates.requests.get', return_value=response) as get:
            download_template(self.stock.template_url)
            self.assertTrue(get.call_args.args[0].startswith('https://'))
            self.assertFalse(get.call_args.kwargs['allow_redirects'])
            self.assertNotIn('headers', get.call_args.kwargs)
            download_template('http://file.autovendpro.com/template.png')
            self.assertEqual(get.call_args.args[0], 'https://file.autovendpro.com/template.png')
            self.assertFalse(get.call_args.kwargs['allow_redirects'])
            self.assertNotIn('headers', get.call_args.kwargs)
        response.status_code = 302
        with patch('management_api.supplier_templates.requests.get', return_value=response):
            with self.assertRaises(TemplateError): download_template(self.stock.template_url)

    def test_endpoint_permissions_scope_csrf_and_audit(self):
        reader = User.objects.create_user('template-reader', is_staff=True)
        reader.user_permissions.add(Permission.objects.get(codename='view_phonemodel'))
        client = APIClient(); client.force_authenticate(reader)
        url = f'/api/v1/admin/phone-models/{self.model.pk}/import-template/'
        self.assertEqual(client.get(f'/api/v1/admin/phone-models/{self.model.pk}/').data['template_sources'][0]['id'], self.stock.pk)
        self.assertEqual(client.post(url, {'source': self.stock.pk}, format='json').status_code, 403)
        reader.user_permissions.add(Permission.objects.get(codename='change_phonemodel'))
        client.force_authenticate(User.objects.get(pk=reader.pk))
        self.assertEqual(client.post(url, {'source': 9999}, format='json').status_code, 400)
        with patch('management_api.supplier_templates.download_template', return_value=png()):
            response = client.post(url, {'source': self.stock.pk}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['image'].startswith('/media/'))
        self.assertTrue(AuditLog.objects.filter(action='sync', object_id=str(self.model.pk)).exists())
        csrf_client = APIClient(enforce_csrf_checks=True); csrf_client.force_login(reader)
        self.assertEqual(csrf_client.post(url, {'source': self.stock.pk}).status_code, 403)
