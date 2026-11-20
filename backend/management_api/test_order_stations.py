import hashlib
from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase
from django.utils import timezone
from . import test_device_info as device_tests
from .models import PrintOrder, SupplierOrder, Device, DeviceProduct, DeviceProviderConnection


class OrderStationTests(TestCase):
    def setUp(self):
        device_tests.PublicDeviceInfoTests.setUp(self)
        self.device.provider_profile['coordinates'] = {'latitude': '23.1', 'longitude': '113.3', 'coordinate_type': 'WGS84'}
        self.device.save()
        self.stock.product.specs=[{'spec_name':'版本','spec_value':'普通款'}];self.stock.product.save()

    def order(self, **values):
        self.client.credentials(HTTP_X_ORDER_KEY='a'*64)
        return PrintOrder.objects.create(mode='airwallex_live', status='paid', paid_at=timezone.now(),
            amount='1.00', case_material='standard', model_name='Test phone', owner_hash=hashlib.sha256(('a'*64).encode()).hexdigest(), **values)

    def public(self, extra=''):
        return self.client.get('/api/v1/store/print-stations/?model=Test%20phone&case_material=standard'+extra)

    def test_public_catalog_is_exact_stocked_model_only_and_never_writes_supplier(self):
        with patch('management_api.device_provider.DeviceProvider') as provider:
            response=self.public()
        provider.assert_not_called()
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(len(response.data['results']),1)
        self.assertEqual(response.data['results'][0]['quantity'],2)
        self.assertEqual(response.data['results'][0]['availability'],'available')
        self.assertIn('no-store',response['Cache-Control'])
        for secret in ['secret-key','device_password','last_login_ip','template_url','owner_hash']:
            self.assertNotIn(secret,str(response.data))
        self.assertEqual(self.client.get('/api/v1/store/print-stations/?model=Test%20phone%20MagSafe').data['results'],[])
        self.assertEqual(SupplierOrder.objects.count(),0)

    def test_empty_stale_incomplete_disabled_and_ambiguous_are_not_recommended(self):
        for field,value in [('stock',0),('template_mask',''),('present',False),('observed_at',timezone.now()-timedelta(minutes=16))]:
            original=getattr(self.stock,field);setattr(self.stock,field,value);self.stock.save()
            self.assertEqual(self.public().data['results'],[],field)
            setattr(self.stock,field,original);self.stock.save()
        self.device.active=False;self.device.save()
        self.assertEqual(self.public().data['results'],[])
        self.device.active=True;self.device.save()
        other=DeviceProviderConnection.objects.create(name='Other',shop_id='146',base_url='https://shop.autovendpro.com')
        Device.objects.create(connection=other,vendor_device_id='401',name='Ambiguous')
        self.assertEqual(self.public().data['results'],[])

    def test_scoped_stock_distinguishes_out_of_stock_and_unknown(self):
        self.stock.stock=0;self.stock.save()
        response=self.public('&shop_id=146&device_id=401')
        self.assertEqual(response.data['results'][0]['availability'],'out_of_stock')
        self.stock.observed_at=timezone.now()-timedelta(minutes=16);self.stock.save()
        response=self.public('&shop_id=146&device_id=401')
        self.assertEqual(response.data['results'][0]['availability'],'updating')
        self.assertIsNone(response.data['results'][0]['quantity'])
        self.assertEqual(self.public('&device_id=401').status_code,400)

    def test_order_access_ownership_shipping_refunds_and_test_modes(self):
        from .models import PrintRefund
        order=self.order();url=f'/api/v1/store/orders/{order.reference}/stations/'
        self.assertEqual(self.client.get(url).data['results'][0]['quantity'],2)
        self.assertEqual(self.client.post(url,{},format='json').status_code,405)
        self.client.credentials(HTTP_X_ORDER_KEY='b'*64)
        self.assertEqual(self.client.get(url).status_code,404)
        self.client.credentials(HTTP_X_ORDER_KEY='a'*64)
        for values in [{'fulfillment_type':'courier'},{'fulfillment_type':'air'},{'mode':'airwallex_test'},{'status':'ready'}]:
            PrintOrder.objects.filter(pk=order.pk).update(**{'fulfillment_type':'pickup','mode':'airwallex_live','status':'paid',**values})
            self.assertFalse(self.client.get(url).data['applicable'])
            self.assertEqual(self.client.get(url).data['results'],[])
        PrintOrder.objects.filter(pk=order.pk).update(status='paid',mode='airwallex_live',fulfillment_type='pickup')
        PrintRefund.objects.create(order=order,amount='1.00',currency='USD',reason='test',status='pending')
        self.assertFalse(self.client.get(url).data['applicable'])

    def test_bound_order_keeps_target_and_checks_its_exact_stock(self):
        order=self.order();url=f'/api/v1/store/orders/{order.reference}/stations/'
        row=SupplierOrder.objects.create(order=order,device=self.device,inventory_item=self.stock,business_number='1',goods_id=10,order_revision=1,snapshot_sha256='a'*64,state='prepared')
        self.stock.stock=0;self.stock.save()
        data=self.client.get(url+'?device_id=999&shop_id=146').data
        self.assertTrue(data['bound']);self.assertEqual(len(data['results']),1)
        self.assertEqual(data['results'][0]['device_id'],'401')
        self.assertEqual(data['results'][0]['availability'],'out_of_stock')
        row.refresh_from_db();self.assertEqual(row.device_id,self.device.pk)
        row.print_confirmed_at=timezone.now();row.save()
        self.assertFalse(self.client.get(url).data['applicable'])

    def test_catalog_paginates_and_has_bounded_query_count(self):
        for i in range(22):
            device=Device.objects.create(connection=self.device.connection,vendor_device_id=str(500+i),name='Station',provider_profile=self.device.provider_profile)
            DeviceProduct.objects.create(device=device,product=self.stock.product,stock=1,observed_at=timezone.now(),template_url=self.stock.template_url,template_imported_url=self.stock.template_imported_url,template_image='a.png',template_mask='b.png',template_width=600,template_height=1200)
        with self.assertNumQueries(5):
            data=self.public().data
        self.assertEqual(len(data['results']),20);self.assertTrue(data['has_more'])
        self.assertEqual(len(self.public('&page=2').data['results']),3)
        self.assertEqual(self.public('&page=bad').status_code,400)

    def test_coordinates_only_required_for_nearby_discovery(self):
        for coords in [None, {}, {'latitude':'invalid','longitude':113,'coordinate_type':'WGS84'},
                       {'latitude':91,'longitude':113,'coordinate_type':'WGS84'},
                       {'latitude':23,'longitude':113},
                       {'latitude':23,'longitude':113,'coordinate_type':'GCJ02'}]:
            self.device.provider_profile={'coordinates':coords};self.device.save()
            self.assertEqual(self.public().data['results'],[])
            scoped = self.public('&shop_id=146&device_id=401').data['results']
            self.assertEqual(len(scoped), 1)
            self.assertEqual(scoped[0]['availability'], 'available')
            self.assertIsNone(scoped[0]['coordinates'])
            self.assertEqual(SupplierOrder.objects.count(), 0)
        order=self.order()
        row=SupplierOrder.objects.create(order=order,device=self.device,inventory_item=self.stock,business_number='2',goods_id=10,order_revision=1,snapshot_sha256='a'*64,state='prepared')
        bound = self.client.get(f'/api/v1/store/orders/{order.reference}/stations/?device_id=999&shop_id=146').data['results']
        self.assertEqual(len(bound), 1)
        self.assertEqual(bound[0]['device_id'], '401')
        self.assertIsNone(bound[0]['coordinates'])
        row.refresh_from_db();self.assertEqual(row.device_id,self.device.pk)

    def test_coordinate_filter_runs_before_pagination(self):
        self.device.provider_profile={};self.device.save()
        for i in range(21):
            device=Device.objects.create(connection=self.device.connection,vendor_device_id=str(800+i),name='Located',provider_profile={'coordinates':{'latitude':0,'longitude':0,'coordinate_type':'WGS84'}})
            DeviceProduct.objects.create(device=device,product=self.stock.product,stock=1,observed_at=timezone.now(),template_url=self.stock.template_url,template_imported_url=self.stock.template_imported_url,template_image='a.png',template_mask='b.png',template_width=600,template_height=1200)
        first=self.public().data;second=self.public('&page=2').data
        self.assertEqual(len(first['results']),20);self.assertTrue(first['has_more'])
        self.assertEqual(len(second['results']),1);self.assertFalse(second['has_more'])
        self.assertNotIn('401',[s['device_id'] for s in first['results']+second['results']])

    def test_scanned_device_without_coordinates_still_requires_stock_and_template(self):
        self.device.provider_profile = {}
        self.device.save()
        for field, value, expected in [('stock', 0, 'out_of_stock'),
                ('template_mask', '', 'unavailable'), ('present', False, 'unavailable'),
                ('observed_at', timezone.now()-timedelta(minutes=16), 'updating')]:
            original = getattr(self.stock, field)
            setattr(self.stock, field, value)
            self.stock.save()
            data = self.public('&shop_id=146&device_id=401').data
            self.assertEqual(data['results'][0]['availability'], expected, field)
            setattr(self.stock, field, original)
            self.stock.save()
        self.assertEqual(self.public('&shop_id=999&device_id=401').data['results'], [])
        self.device.active = False
        self.device.save()
        self.assertEqual(self.public('&shop_id=146&device_id=401').data['results'], [])
        self.assertEqual(SupplierOrder.objects.count(), 0)
