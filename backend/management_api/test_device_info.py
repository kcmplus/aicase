import copy
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient
from .device_discovery import discover_devices
from .device_provider import ProviderError
from .models import DeviceProviderConnection, Device, Brand, PhoneModel, SupplierProduct, DeviceProduct


class DeviceDiscoveryTests(TestCase):
    def setUp(self):
        self.connection=DeviceProviderConnection.objects.create(name='test',base_url='https://shop.widermatrix.cn',shop_id='146')
        self.device=Device.objects.create(connection=self.connection,vendor_device_id='401',name='Our display name',location_note='Keep me')
        self.rows=[{'id':401,'shop_id':146,'device_name':'Vendor name','device_num':'WM-401','is_deleted':0,
                    'device_password':'private-password','contact_tel':'private-phone','total_money':900},
                   {'id':400,'shop_id':146,'device_name':None,'device_num':'WM-400','is_deleted':0}]

    def discover(self, pages=None):
        provider=MagicMock()
        provider.devices.side_effect=pages or [{'page':1,'totalNum':2,'totalPages':1,'list':self.rows}]
        with patch('management_api.device_discovery.DeviceProvider',return_value=provider):
            result=discover_devices(self.connection)
        return result,provider

    def test_discovery_preserves_local_settings_and_discards_private_vendor_fields(self):
        result,_=self.discover()
        self.assertEqual((result['created'],result['updated']),(1,1))
        self.device.refresh_from_db()
        self.assertEqual((self.device.name,self.device.location_note,self.device.active),('Our display name','Keep me',True))
        self.assertEqual(self.device.provider_profile,{'device_name':'Vendor name','device_num':'WM-401'})
        new=Device.objects.get(vendor_device_id='400')
        self.assertFalse(new.active)
        self.assertEqual(new.name,'WM-400')
        self.assertEqual(self.discover()[0]['created'],0)
        self.assertEqual(Device.objects.count(),2)

    def test_pagination_and_partial_failure_never_publish_partial_devices(self):
        rows=[{**self.rows[0],'id':1000+i} for i in range(101)]
        pages=[{'page':1,'totalNum':101,'totalPages':2,'list':rows[:100]},
               {'page':2,'totalNum':101,'totalPages':2,'list':rows[100:]}]
        bad=copy.deepcopy(pages);bad[1]['list'][0]['shop_id']=999
        with self.assertRaises(ProviderError):self.discover(bad)
        self.assertEqual(Device.objects.count(),1)
        result,provider=self.discover(pages)
        self.assertEqual(result['created'],101)
        self.assertEqual(provider.devices.call_args.kwargs,{'page':2,'limit':100})

    def test_empty_does_not_delete_and_duplicate_or_changed_counts_are_rejected(self):
        self.discover([{'page':1,'totalNum':0,'totalPages':0,'list':[]}])
        self.assertTrue(Device.objects.filter(pk=self.device.pk,active=True).exists())
        for data in [
            {'page':1,'totalNum':2,'totalPages':1,'list':[self.rows[0],self.rows[0]]},
            {'page':1,'totalNum':3,'totalPages':1,'list':self.rows},
            {'page':1,'totalNum':10001,'totalPages':101,'list':[]},
        ]:
            with self.subTest(data=data),self.assertRaises(ProviderError):self.discover([data])

    def test_connection_revision_change_rejects_publication(self):
        def changed(**kwargs):
            DeviceProviderConnection.objects.filter(pk=self.connection.pk).update(revision=2)
            return {'page':1,'totalNum':2,'totalPages':1,'list':self.rows}
        provider=MagicMock();provider.devices.side_effect=changed
        with patch('management_api.device_discovery.DeviceProvider',return_value=provider),self.assertRaises(ProviderError):
            discover_devices(self.connection)
        self.assertEqual(Device.objects.count(),1)

    def test_discovery_endpoint_is_superuser_only_and_audited(self):
        client=APIClient();user=User.objects.create_user('reader',is_staff=True)
        client.force_authenticate(user)
        url=f'/api/v1/admin/device-connections/{self.connection.pk}/sync-devices/'
        self.assertEqual(client.post(url,{},format='json').status_code,403)
        user.is_superuser=True;user.save();client.force_authenticate(user)
        with patch('management_api.device_discovery.DeviceProvider') as provider:
            provider.return_value.devices.return_value={'page':1,'totalNum':2,'totalPages':1,'list':self.rows}
            self.assertEqual(client.post(url,{},format='json').status_code,200)
        from .models import AuditLog
        self.assertTrue(AuditLog.objects.filter(actor=user,action='sync').exists())
        csrf=APIClient(enforce_csrf_checks=True);csrf.force_login(user)
        self.assertEqual(csrf.post(url,{},format='json').status_code,403)


class PublicDeviceInfoTests(TestCase):
    def setUp(self):
        connection=DeviceProviderConnection.objects.create(name='secret merchant name',base_url='https://shop.widermatrix.cn',shop_id='146',api_key_ciphertext='secret-key')
        self.device=Device.objects.create(connection=connection,vendor_device_id='401',name='Test station',
            provider_profile={'device_num':'WM-401','device_password':'do-not-expose'},
            provider_config={'currency':'USD','print_type':'600dpi','last_login_ip':'private-ip'},last_success_at=timezone.now())
        brand=Brand.objects.create(code='test',name='Test')
        model=PhoneModel.objects.create(code='test',name='Test phone',brand=brand)
        product=SupplierProduct.objects.create(connection=connection,goods_id='10',product_id='1',name='Phone',phone_model=model,active=True)
        self.stock=DeviceProduct.objects.create(device=self.device,product=product,stock=2,observed_at=timezone.now(),
            template_url='https://example.com/a.png',template_imported_url='https://example.com/a.png',
            template_image='a.png',template_mask='b.png',template_width=600,template_height=1200)
        self.client=APIClient();self.url='/api/v1/store/device-info/?shop_id=146&device_id=401'

    def test_public_projection_has_real_identity_but_no_secrets_or_online_guess(self):
        response=self.client.get(self.url)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data['number'],'WM-401')
        self.assertEqual(response.data['inventory']['model_count'],1)
        self.assertEqual(response.data['online_status'],'unknown')
        self.assertFalse(response.data['fulfillment_connected'])
        for private in ('secret','private-ip','device_password','template_url','provider_config'):
            self.assertNotIn(private,str(response.data))
        self.assertIn('no-store',response['Cache-Control'])

    def test_stale_inventory_is_not_offered_as_ready(self):
        self.stock.observed_at=timezone.now()-timedelta(minutes=16);self.stock.save()
        response=self.client.get(self.url)
        self.assertEqual(response.data['inventory']['availability'],'updating')
        self.assertEqual(response.data['models'],[])

    def test_scope_disabled_and_ambiguous_devices_do_not_fall_back(self):
        self.assertEqual(self.client.get('/api/v1/store/device-info/?device_id=401').status_code,400)
        self.assertEqual(self.client.get(self.url.replace('401','999')).status_code,404)
        self.device.active=False;self.device.save()
        self.assertEqual(self.client.get(self.url).status_code,404)
        self.device.active=True;self.device.save()
        other=DeviceProviderConnection.objects.create(name='Other',base_url='https://shop.autovendpro.com',shop_id='146')
        Device.objects.create(connection=other,vendor_device_id='401',name='Other')
        self.assertEqual(self.client.get(self.url).status_code,404)
