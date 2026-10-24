import copy
import uuid
from io import StringIO, BytesIO
import base64
from django.contrib.auth.models import User, Group
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient
from PIL import Image
from .models import PrintOrder, PricingPlan, PhoneModel, AuditLog

class StoreOrderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_catalog', stdout=StringIO())
        cls.support=User.objects.create_user('order-support', is_staff=True)
        cls.support.groups.add(Group.objects.get(name='客服人员'))
    def setUp(self):
        cache.clear()
        self.client=APIClient(enforce_csrf_checks=True)
        self.client.credentials(HTTP_X_ORDER_KEY='a'*64)
        self.payload={'request_key':str(uuid.uuid4()),'accepted':True,'expected_amount':'10.00','customer_email':'example@example.com','snapshot':{'version':2,'code':'POP-C-0123456789ABCDEF','source':'collection','designId':'bloom','model':'iPhone 16 Pro','photo':'','effect':'original','intensity':65,'zoom':100,'x':50,'y':50}}
    def create(self):
        response=self.client.post('/api/v1/store/orders/',self.payload,format='json')
        self.assertEqual(response.status_code,201,response.data)
        return response.data
    def endpoint(self, order):
        return f"/api/v1/store/orders/{order['reference']}/"
    def action(self, order, action, **extra):
        return self.client.post(self.endpoint(order)+'actions/', {'revision':order['revision'],'action':action,'code':order['snapshot']['code'],**extra},format='json')
    def test_checkout_persists_authoritative_price_private_snapshot_and_no_real_payment(self):
        order=self.create()
        self.assertEqual(order['mode'],'demo')
        self.assertEqual(order['status'],'paid')
        self.assertEqual(str(order['amount']),'10.00')
        self.assertEqual(PrintOrder.objects.get().snapshot['designId'],'bloom')
        self.assertEqual(self.client.get(self.endpoint(order))['Cache-Control'].find('no-store')>=0,True)
        listed=self.client.get('/api/v1/store/orders/').json()['results'][0]
        for private in ('snapshot','owner_hash','request_key','customer_email','code'):
            self.assertNotIn(private,listed)
        self.assertNotIn('example@example.com',str(list(AuditLog.objects.values())))
    def test_repeat_checkout_returns_same_order_even_after_price_change(self):
        order=self.create()
        PricingPlan.objects.filter(kind='print').update(price='15.00')
        result=self.client.post('/api/v1/store/orders/',self.payload,format='json')
        self.assertEqual(result.status_code,200,result.data)
        self.assertEqual(result.data['reference'],order['reference'])
        self.assertEqual(PrintOrder.objects.count(),1)
        self.assertEqual(str(result.data['amount']),'10.00')
    def test_server_rejects_price_tampering_unknown_fields_and_missing_consent(self):
        for patch in ({'expected_amount':'0.01'}, {'status':'paid'}, {'amount':'0.01'},{'accepted':False},{'customer_email':'not email'}):
            data={**self.payload,**patch}
            result=self.client.post('/api/v1/store/orders/',data,format='json')
            self.assertIn(result.status_code,(400,409),result.data)
        self.assertFalse(PrintOrder.objects.exists())
    def test_disabled_plan_or_model_rejects_order(self):
        PricingPlan.objects.filter(kind='print').update(active=False)
        self.assertEqual(self.client.post('/api/v1/store/orders/',self.payload,format='json').status_code,409)
        PricingPlan.objects.filter(kind='print').update(active=True)
        PhoneModel.objects.filter(name=self.payload['snapshot']['model']).update(active=False)
        self.assertEqual(self.client.post('/api/v1/store/orders/',self.payload,format='json').status_code,400)
    def test_other_browser_and_anonymous_cannot_access_or_change_order(self):
        order=self.create()
        self.client.credentials(HTTP_X_ORDER_KEY='b'*64)
        self.assertEqual(self.client.get('/api/v1/store/orders/').json()['results'],[])
        self.assertEqual(self.client.get(self.endpoint(order)).status_code,404)
        self.assertEqual(self.action(order,'cancel').status_code,404)
        self.assertEqual(self.client.patch(self.endpoint(order),{},format='json').status_code,404)
        self.assertEqual(self.client.post('/api/v1/store/orders/',self.payload,format='json').status_code,409)
        self.client.credentials()
        self.assertEqual(self.client.get('/api/v1/store/orders/').status_code,403)
        self.assertEqual(self.client.get(self.endpoint(order)).status_code,403)
    def test_photo_and_layers_are_preserved_but_invalid_images_or_markup_rejected(self):
        stream=BytesIO();Image.new('RGB',(20,20),'red').save(stream,format='PNG')
        photo='data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode()
        self.payload['snapshot'].update(source='photo',photo=photo,addedArtwork=[{'id':'extra-one','type':'text','text':'<script>alert(1)</script>','font':'serif','color':'#123456','x':50,'y':50,'scale':100,'rotation':0}])
        order=self.create()
        self.assertEqual(order['snapshot']['photo'],photo)
        self.assertEqual(order['snapshot']['addedArtwork'][0]['text'],'<script>alert(1)</script>')
        for photo in ('https://example.com/photo.jpg','data:image/svg+xml;base64,PHN2Zz4=','data:image/png;base64,YmFk'):
            self.payload['request_key']=str(uuid.uuid4());self.payload['snapshot']['photo']=photo
            self.assertEqual(self.client.post('/api/v1/store/orders/',self.payload,format='json').status_code,400)
    def test_snapshot_rejects_unknown_layers_and_nonfinite_numbers(self):
        for patch in ({'artworkEdits':{'unknown':{'x':50,'y':50,'scale':100,'rotation':0}}},{'url':'javascript:alert(1)'},{'zoom':'NaN'},{'model':'Nonexistent'},{'designId':'unknown'},{'addedArtwork':[{'id':'extra-x','type':'sticker','asset':'missing','x':50,'y':50,'scale':100,'rotation':0}]}):
            data=copy.deepcopy(self.payload);data['snapshot'].update(patch)
            self.assertEqual(self.client.post('/api/v1/store/orders/',data,format='json').status_code,400)
    def test_revision_keeps_original_price_invalidates_old_code_and_retries_once(self):
        order=self.create();oldcode=order['snapshot']['code']
        snapshot=copy.deepcopy(order['snapshot']);snapshot.update(code='POP-C-FEDCBA9876543210',effect='warm')
        data={'revision':1,'accepted':True,'snapshot':snapshot}
        PricingPlan.objects.filter(kind='print').update(price='99.99',active=False)
        edited=self.client.patch(self.endpoint(order),data,format='json')
        self.assertEqual(edited.status_code,200,edited.data)
        self.assertEqual(str(edited.data['amount']),'10.00')
        self.assertEqual(edited.data['revision'],2)
        repeat=self.client.patch(self.endpoint(order),data,format='json')
        self.assertEqual(repeat.status_code,200,repeat.data)
        self.assertEqual(repeat.data['revision'],2)
        self.assertEqual(self.action(order,'start',station_id='DEMO-01').status_code,409)
        stale=copy.deepcopy(data);stale['snapshot']['code']='POP-C-1111111111111111'
        self.assertEqual(self.client.patch(self.endpoint(order),stale,format='json').status_code,409)
        self.assertNotEqual(oldcode,PrintOrder.objects.get().snapshot['code'])
    def test_station_lifecycle_locked_revision_and_no_repeated_print(self):
        order=self.create()
        self.assertEqual(self.action(order,'collect').status_code,409)
        self.assertEqual(self.action(order,'start',station_id='DEMO-03').status_code,400)
        started=self.action(order,'start',station_id='DEMO-01')
        self.assertEqual(started.status_code,200,started.data)
        self.assertEqual(self.action(order,'start',station_id='DEMO-01').data['revision'],2)
        self.assertEqual(self.client.patch(self.endpoint(order),{'revision':2,'accepted':True,'snapshot':order['snapshot']},format='json').status_code,409)
        ready=self.action(started.data,'ready');self.assertEqual(ready.status_code,200)
        done=self.action(ready.data,'collect');self.assertEqual(done.data['status'],'completed')
        self.assertEqual(self.action(done.data,'start',station_id='DEMO-01').status_code,409)
        self.assertEqual(self.action(done.data,'cancel').status_code,409)
    def test_cancel_idempotent_and_cannot_print(self):
        order=self.create()
        self.assertEqual(self.action(order,'cancel').data['status'],'cancelled')
        self.assertEqual(self.action(order,'cancel').data['revision'],2)
        self.assertEqual(self.action(order,'start',station_id='DEMO-01').status_code,409)
    def test_admin_detail_has_preview_with_permission_and_list_excludes_photos(self):
        order=self.create();pk=PrintOrder.objects.get().pk
        self.client.credentials()
        self.assertEqual(self.client.get(f'/api/v1/admin/orders/{pk}/').status_code,403)
        self.client.force_login(self.support)
        detail=self.client.get(f'/api/v1/admin/orders/{pk}/').json()
        self.assertEqual(detail['snapshot']['code'],order['snapshot']['code'])
        self.assertNotIn('owner_hash',detail)
        self.assertNotIn('snapshot',self.client.get('/api/v1/admin/orders/').json()['results'][0])
        self.assertEqual(self.client.get('/api/v1/admin/orders/?status=cancelled').json()['count'],0)
    def test_pagination_and_rate_limit(self):
        order=self.create();owner_hash=PrintOrder.objects.get().owner_hash
        PrintOrder.objects.bulk_create([PrintOrder(owner_hash=owner_hash,model_name='iPhone 16',amount='10') for _ in range(21)])
        page=self.client.get('/api/v1/store/orders/').json()
        self.assertEqual(len(page['results']),20);self.assertTrue(page['has_more'])
        page=self.client.get('/api/v1/store/orders/?page=2').json()
        self.assertEqual(len(page['results']),2);self.assertFalse(page['has_more'])
        for _ in range(57):self.client.get('/api/v1/store/orders/')
        self.assertEqual(self.client.get('/api/v1/store/orders/').status_code,429)

    def test_non_object_payload_returns_validation_error(self):
        self.assertEqual(self.client.post('/api/v1/store/orders/', [], format='json').status_code,400)
        self.assertEqual(self.client.post('/api/v1/store/orders/', {}, format='json').status_code,400)
