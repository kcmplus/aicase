import hashlib
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from django.core.cache import cache
from rest_framework.test import APIClient
from .models import PrintOrder, SupplierOrder, DeviceProviderConnection, Device, SupplierProduct, DeviceProduct
from .order_progress import order_progress, with_order_progress


class OrderProgressTests(TestCase):
    def setUp(self):
        cache.clear()
        self.order = PrintOrder.objects.create(mode='airwallex_live', status='paid', amount='9.90', paid_at=timezone.now(),
            model_name='Test phone', owner_hash=hashlib.sha256(('a'*64).encode()).hexdigest(),snapshot={'private':'SECRET'})
        c=DeviceProviderConnection.objects.create(name='Private connection',shop_id='351',base_url='https://api.autovendpro.com',api_key_ciphertext='PRIVATE-KEY')
        d=Device.objects.create(connection=c,vendor_device_id='789',name='Station',location_note='Public address')
        p=SupplierProduct.objects.create(connection=c,goods_id='141',product_id='1',name='Phone')
        stock=DeviceProduct.objects.create(device=d,product=p,stock=5,observed_at=timezone.now())
        self.row=SupplierOrder.objects.create(order=self.order,device=d,inventory_item=stock,business_number='123',goods_id=141,
            order_revision=1,snapshot_sha256='a'*64,state='submitted',cloud_synced_at=timezone.now())
        self.client=APIClient();self.client.credentials(HTTP_X_ORDER_KEY='a'*64)

    def progress(self):
        return order_progress(with_order_progress(PrintOrder.objects.all()).get(pk=self.order.pk))

    def test_verified_phases_are_distinct_and_do_not_mutate_payment_or_collection(self):
        for phase in ['printing','printed','delivering','dispensed','print_failed','delivery_failed']:
            self.row.cloud_status={'phase':phase,'phase_verified':True,'payment_recorded':True}
            self.row.save()
            self.assertEqual(self.progress()['code'],phase)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status,'paid')
        self.assertEqual(str(self.order.amount),'9.90')
        self.assertEqual(self.progress()['payment'],'paid')

    def test_unverified_or_unmatched_physical_states_never_claim_printing(self):
        self.row.print_confirmed_at=timezone.now()
        for snapshot in [{},{'phase':'dispensed','phase_verified':False,'payment_recorded':True},
                         {'phase':'printing','print_status':1,'phase_verified':True,'payment_recorded':False}]:
            self.row.cloud_status=snapshot;self.row.save()
            self.assertEqual(self.progress()['code'],'unverified')
        self.row.print_confirmed_at=None
        self.row.cloud_status={'print_status':99,'shipment_status':0};self.row.save()
        self.assertEqual(self.progress()['code'],'unverified')

    def test_cancelled_test_delivery_and_unpaid_orders_have_separate_meaning(self):
        self.row.cloud_status={'phase':'printing','phase_verified':True,'payment_recorded':True,'status':4};self.row.save()
        self.assertEqual(self.progress()['code'],'cancelled')
        self.order.mode='stripe_test';self.order.save()
        self.assertEqual(self.progress()['code'],'test')
        self.order.fulfillment_type='courier';self.order.save()
        self.assertEqual(self.progress()['code'],'delivery')
        self.order.fulfillment_type='pickup';self.order.mode='airwallex_live';self.order.paid_at=None;self.order.status='pending';self.order.save()
        self.row.cloud_status={'phase':'printing','phase_verified':True,'payment_recorded':True};self.row.save()
        self.assertEqual(self.progress()['code'],'awaiting_payment')
        self.assertEqual(self.progress()['payment'],'unpaid')

    def test_stale_keeps_last_verified_stage_and_time(self):
        stamp=timezone.now()-timedelta(minutes=2)
        self.row.cloud_synced_at=stamp
        self.row.cloud_status={'phase':'printing','phase_verified':True,'payment_recorded':True};self.row.save()
        data=self.progress()
        self.assertTrue(data['stale']);self.assertEqual(data['updated_at'],stamp);self.assertEqual(data['code'],'printing')

    def test_list_detail_progress_match_and_are_private_read_only(self):
        url=f'/api/v1/store/orders/{self.order.reference}/'
        with patch('management_api.device_provider.DeviceProvider') as provider:
            listing=self.client.get('/api/v1/store/orders/').data['results'][0]
            detail=self.client.get(url).data
            response=self.client.get(url+'progress/')
        provider.assert_not_called()
        self.assertEqual(response.status_code,200)
        self.assertEqual(listing['progress'],detail['progress'])
        self.assertEqual(detail['progress'],response.data['progress'])
        self.assertEqual(response.data['progress']['code'],'awaiting_confirmation')
        for forbidden in ['SECRET','PRIVATE-KEY','snapshot','customer_email','trade_no','print_image','file_token']:
            self.assertNotIn(forbidden,str(response.data))
            self.assertNotIn(forbidden,str(listing))
        self.assertIn('no-store',response['Cache-Control'])
        self.assertEqual(self.client.post(url+'progress/',{},format='json').status_code,405)
        self.client.credentials(HTTP_X_ORDER_KEY='b'*64)
        self.assertEqual(self.client.get(url+'progress/').status_code,404)
        self.assertEqual(self.client.get('/api/v1/store/orders/').data['results'],[])

    def test_admin_filter_uses_same_projection_and_progress_cannot_be_edited(self):
        root=User.objects.create_superuser('root',password='test-only')
        self.client.force_authenticate(root)
        self.row.cloud_status={'phase':'printed','phase_verified':True,'payment_recorded':True};self.row.save()
        response=self.client.get('/api/v1/admin/orders/?progress=printing')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data['count'],1)
        self.assertEqual(response.data['results'][0]['progress']['code'],'printed')
        self.assertEqual(self.client.get('/api/v1/admin/orders/?progress=attention').data['count'],0)
        url=f'/api/v1/admin/orders/{self.order.pk}/progress/'
        self.assertEqual(self.client.get(url).data['progress'],response.data['results'][0]['progress'])
        self.assertEqual(self.client.patch(f'/api/v1/admin/orders/{self.order.pk}/',{'progress':{'code':'dispensed'}},format='json').status_code,400)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(url).status_code,403)

    def test_list_projection_does_not_add_one_query_per_order(self):
        for i in range(3):PrintOrder.objects.create(mode='demo',amount=0,model_name='Other')
        with self.assertNumQueries(1):
            rows=list(with_order_progress(PrintOrder.objects.all()).defer('snapshot'))
            for order in rows:order_progress(order)

    def test_refund_does_not_erase_verified_physical_progress_and_zero_is_not_payment(self):
        from .models import PrintRefund
        PrintRefund.objects.create(order=self.order,amount='9.90',currency='USD',reason='test',status='pending')
        self.assertEqual(self.progress()['code'],'refund_pending')
        self.row.cloud_status={'phase':'dispensed','phase_verified':True,'payment_recorded':True};self.row.save()
        self.assertEqual(self.progress()['code'],'dispensed')
        self.order.mode='free_test';self.order.amount=0;self.order.paid_at=None;self.order.save()
        self.assertNotEqual(self.progress()['code'],'dispensed')
        self.assertNotEqual(self.progress()['payment'],'free')
