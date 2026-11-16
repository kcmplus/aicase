import copy
import uuid
from io import StringIO, BytesIO
import base64
from django.contrib.auth.models import User, Group, Permission
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from PIL import Image
from .models import PrintOrder, PricingPlan, PhoneModel, AuditLog, Customer

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
    def login_customer(self, csrf=True):
        customer=Customer.objects.create(email='member@example.com',verified_at=timezone.now())
        session=self.client.session
        session['store_customer_id']=str(customer.pk)
        session['store_customer_version']=customer.session_version
        session.save()
        self.payload['customer_id']=str(customer.pk)
        if csrf:
            token=self.client.get('/api/v1/auth/csrf/').data['csrfToken']
            self.client.credentials(HTTP_X_ORDER_KEY='a'*64,HTTP_X_CSRFTOKEN=token)
        return customer
    def test_signed_in_checkout_uses_verified_email_and_customer(self):
        customer=self.login_customer()
        self.payload['customer_email']='untrusted invalid email'
        order=self.create()
        saved=PrintOrder.objects.get()
        self.assertEqual(saved.customer,customer)
        self.assertEqual(order['customer_email'],customer.email)
        self.assertNotIn('customer_id',order)
        # A shared login does not replace the existing private browser order key.
        self.client.credentials(HTTP_X_ORDER_KEY='b'*64)
        self.assertEqual(self.client.get(self.endpoint(order)).status_code,404)
    def test_signed_in_checkout_requires_csrf(self):
        self.login_customer(csrf=False)
        response=self.client.post('/api/v1/store/orders/',self.payload,format='json')
        self.assertEqual(response.status_code,403)
        self.assertFalse(PrintOrder.objects.exists())
    def test_guest_can_leave_email_blank_or_type_it_without_linking_an_account(self):
        Customer.objects.create(email='member@example.com',verified_at=timezone.now())
        for email in ('', 'guest@example.com', 'member@example.com'):
            self.payload.update(request_key=str(uuid.uuid4()),customer_email=email,customer_id=None)
            order=self.create()
            self.assertEqual(order['customer_email'],email)
            self.assertIsNone(PrintOrder.objects.get(reference=order['reference']).customer_id)
    def test_client_cannot_assign_customer_or_silently_use_a_changed_session(self):
        self.payload['customer_id']=str(uuid.uuid4())
        self.assertEqual(self.client.post('/api/v1/store/orders/',self.payload,format='json').status_code,409)
        customer=self.login_customer()
        for expected in (None,str(uuid.uuid4())):
            self.payload['customer_id']=expected
            self.assertEqual(self.client.post('/api/v1/store/orders/',self.payload,format='json').status_code,409)
        self.payload['customer_id']=str(customer.pk)
        Customer.objects.filter(pk=customer.pk).update(session_version=1)
        self.assertEqual(self.client.post('/api/v1/store/orders/',self.payload,format='json').status_code,409)
        self.assertFalse(PrintOrder.objects.exists())
    def test_retry_after_sign_in_keeps_the_original_guest_contact_and_identity(self):
        order=self.create()
        self.login_customer()
        response=self.client.post('/api/v1/store/orders/',self.payload,format='json')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data['reference'],order['reference'])
        saved=PrintOrder.objects.get()
        self.assertEqual(saved.customer_email,'example@example.com')
        self.assertIsNone(saved.customer_id)
    def test_admin_customer_link_is_read_only_and_does_not_grant_customer_access(self):
        customer=self.login_customer()
        self.create();saved=PrintOrder.objects.get()
        viewer=User.objects.create_user('order-only',is_staff=True)
        viewer.user_permissions.add(Permission.objects.get(codename='view_printorder'),Permission.objects.get(codename='change_printorder'))
        admin=APIClient();admin.force_authenticate(viewer)
        url=f'/api/v1/admin/orders/{saved.pk}/'
        self.assertEqual(admin.get(url).data['customer_id'],str(customer.pk))
        self.assertEqual(admin.get('/api/v1/admin/orders/').data['results'][0]['customer_id'],str(customer.pk))
        self.assertEqual(admin.get(f'/api/v1/admin/customers/{customer.pk}/').status_code,403)
        self.assertEqual(admin.patch(url,{'customer_id':None},format='json').status_code,400)
        self.assertEqual(admin.patch(url,{'notes':'Handled'},format='json').status_code,200)
        customer.delete();saved.refresh_from_db()
        self.assertIsNone(saved.customer_id)
        self.assertEqual(saved.customer_email,'member@example.com')
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
    def test_order_list_reports_refund_status_consistently_with_detail(self):
        from .models import PrintRefund
        order = self.create()
        PrintRefund.objects.create(order=PrintOrder.objects.get(reference=order['reference']),
                                   status='succeeded', amount='10.00', currency='USD', reason='test')
        detail = self.client.get(self.endpoint(order)).json()
        listed = self.client.get('/api/v1/store/orders/').json()['results'][0]
        self.assertEqual(detail['refund']['status'], 'succeeded')
        self.assertEqual(listed.get('refund', {}).get('status'), 'succeeded',
                         'The order list must display the actual refund state')
    def test_order_list_refunds_are_public_read_only_and_owned_without_per_order_queries(self):
        from .models import PrintRefund
        for status in (None, 'requested', 'pending', 'succeeded', 'failed'):
            self.payload['request_key'] = str(uuid.uuid4())
            order = self.create()
            if status:
                PrintRefund.objects.create(order=PrintOrder.objects.get(reference=order['reference']),
                                           status=status, amount='10.00', currency='USD',
                                           reason='private support note', provider_id='private-provider-id')
        orders_before = list(PrintOrder.objects.order_by('pk').values())
        refunds_before = list(PrintRefund.objects.order_by('pk').values())
        # A list read must neither reconcile external refunds nor write state;
        # all refund states are loaded with the owned orders in one query.
        with self.assertNumQueries(1):
            response = self.client.get('/api/v1/store/orders/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        rows = response.json()['results']
        self.assertEqual(len(rows), 5)
        self.assertFalse(response.json()['has_more'])
        self.assertEqual([row['refund']['status'] if row['refund'] else None for row in rows],
                         ['failed', 'succeeded', 'pending', 'requested', None])
        for row in rows:
            detail = self.client.get(self.endpoint(row)).json()
            self.assertEqual(row['refund'], detail['refund'])
            self.assertEqual(row['status'], 'paid')  # Preserve historical order status.
            for private in ('snapshot', 'owner_hash', 'request_key', 'customer_email', 'code'):
                self.assertNotIn(private, row)
            if row['refund']:
                self.assertEqual(set(row['refund']), {'reference', 'status', 'amount', 'currency', 'created_at', 'completed_at'})
        self.assertNotIn('private support note', response.content.decode())
        self.assertNotIn('private-provider-id', response.content.decode())
        self.assertEqual(list(PrintOrder.objects.order_by('pk').values()), orders_before)
        self.assertEqual(list(PrintRefund.objects.order_by('pk').values()), refunds_before)
        self.client.credentials(HTTP_X_ORDER_KEY='b'*64)
        self.assertEqual(self.client.get('/api/v1/store/orders/').json()['results'], [])
        self.assertEqual(self.client.get(self.endpoint(rows[0])).status_code, 404)
        self.client.credentials()
        self.assertEqual(self.client.get('/api/v1/store/orders/').status_code, 403)
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

    def test_single_quantity_is_strict_on_create_and_idempotent_retry(self):
        invalid = [0, 2, -1, True, False, '1', 1.0, None, [], {}]
        for quantity in invalid:
            with self.subTest(quantity=quantity):
                response = self.client.post('/api/v1/store/orders/', {**self.payload, 'quantity': quantity}, format='json')
                self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(PrintOrder.objects.exists())
        self.payload['quantity'] = 1
        order = self.create()
        before = list(PrintOrder.objects.values())
        for quantity in invalid:
            response = self.client.post('/api/v1/store/orders/', {**self.payload, 'quantity': quantity}, format='json')
            self.assertEqual(response.status_code, 400)
        for patch in ({'count': 2}, {'copies': 2}, {'amount': '20.00'},
                      {'snapshot': {**self.payload['snapshot'], 'quantity': 2}}):
            self.assertEqual(self.client.post('/api/v1/store/orders/', {**self.payload, **patch}, format='json').status_code, 400)
        self.assertEqual(list(PrintOrder.objects.values()), before)
        self.assertEqual(self.client.post('/api/v1/store/orders/', self.payload, format='json').data['reference'], order['reference'])

    def test_single_quantity_revision_cannot_override_frozen_amount(self):
        order = self.create()
        snapshot = {**order['snapshot'], 'code': 'POP-C-FEDCBA9876543210'}
        payload = {'revision': 1, 'accepted': True, 'snapshot': snapshot, 'quantity': 2}
        self.assertEqual(self.client.patch(self.endpoint(order), payload, format='json').status_code, 400)
        payload['quantity'] = 1
        response = self.client.patch(self.endpoint(order), payload, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(str(response.data['amount']), '10.00')
        payload['quantity'] = 2
        self.assertEqual(self.client.patch(self.endpoint(order), payload, format='json').status_code, 400)
        self.assertEqual(PrintOrder.objects.get().revision, 2)

    def test_qa_revision_rejects_quantity_types_aliases_and_nested_bypasses(self):
        order = self.create()
        before = list(PrintOrder.objects.values())
        base = {'revision': 1, 'accepted': True,
                'snapshot': {**self.payload['snapshot'], 'code': 'POP-C-FEDCBA9876543210'}}
        patches = [{'quantity': value} for value in
                   (0, 2, -1, True, False, '1', 1.0, None, [], {})]
        patches += [{'copies': 2}, {'count': 2},
                    {'snapshot': {**base['snapshot'], 'quantity': 2}},
                    {'snapshot': {**base['snapshot'], 'copies': 2}}]
        for patch in patches:
            with self.subTest(patch=patch):
                response = self.client.patch(self.endpoint(order), {**base, **patch}, format='json')
                self.assertEqual(response.status_code, 400, response.data)
                self.assertEqual(list(PrintOrder.objects.values()), before)

    def test_historical_multi_snapshot_reads_and_retry_never_recalculate(self):
        order = self.create()
        original = PrintOrder.objects.get()
        original.snapshot = {**original.snapshot, 'quantity': 3}
        original.amount = '30.00'
        original.save()
        for status in ('pending', 'paid', 'printing', 'completed', 'cancelled'):
            PrintOrder.objects.filter(pk=original.pk).update(status=status)
            before = list(PrintOrder.objects.values())
            detail = self.client.get(self.endpoint(order))
            self.assertEqual(detail.data['snapshot']['quantity'], 3)
            self.assertEqual(str(detail.data['amount']), '30.00')
            self.client.get('/api/v1/store/orders/')
            retry = self.client.post('/api/v1/store/orders/', self.payload, format='json')
            self.assertEqual(retry.status_code, 200)
            self.assertEqual(retry.data['snapshot']['quantity'], 3)
            self.assertEqual(list(PrintOrder.objects.values()), before)
            revision = {'revision': original.revision, 'accepted': True, 'quantity': 1,
                        'snapshot': {**self.payload['snapshot'], 'code': 'POP-C-FEDCBA9876543210'}}
            self.assertEqual(self.client.patch(self.endpoint(order), revision, format='json').status_code, 409)
            self.assertEqual(list(PrintOrder.objects.values()), before)

    def test_photo_fit_is_frozen_in_order_snapshot_and_unknown_modes_rejected(self):
        stream=BytesIO(); Image.new('RGB',(40,20),'red').save(stream,format='PNG')
        photo='data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode()
        self.payload['snapshot'].update(source='photo',photo=photo)
        for fit in ('cover','contain','blur'):
            self.payload['request_key']=str(uuid.uuid4())
            self.payload['snapshot']['photoPlacement']={'x':50,'y':50,'scale':100,'rotation':0,'fit':fit}
            order=self.create()
            self.assertEqual(order['snapshot']['photoPlacement']['fit'],fit)
            self.assertEqual(self.client.get(self.endpoint(order)).data['snapshot']['photoPlacement']['fit'],fit)
        self.payload['request_key']=str(uuid.uuid4())
        self.payload['snapshot']['photoPlacement']['fit']='remote-image'
        self.assertEqual(self.client.post('/api/v1/store/orders/',self.payload,format='json').status_code,400)
        self.assertEqual(PrintOrder.objects.count(),3)
