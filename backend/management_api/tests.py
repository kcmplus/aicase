from io import BytesIO, StringIO
import tempfile
from django.contrib.auth.models import User, Group, Permission
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from PIL import Image
from .models import Brand, PhoneModel, Graphic, DesignTemplate, AIStyle, PricingPlan, PrintOrder, AuditLog

PASSWORD = 'Local-test-only!739152'

class ManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_catalog', stdout=StringIO())
        cls.root = User.objects.create_superuser('root', password=PASSWORD)
        cls.reader = User.objects.create_user('reader', password=PASSWORD, is_staff=True)
        cls.reader.groups.add(Group.objects.get(name='只读人员'))
        cls.operator = User.objects.create_user('operator', password=PASSWORD, is_staff=True)
        cls.operator.groups.add(Group.objects.get(name='运营管理员'))
        cls.support = User.objects.create_user('support', password=PASSWORD, is_staff=True)
        cls.support.groups.add(Group.objects.get(name='客服人员'))

    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def as_user(self, user):
        self.client.force_login(user)

    def test_anonymous_cannot_read_or_modify_admin_resources(self):
        for resource in ('brands','phone-models','designs','graphics','ai-styles','ai-examples','plans','orders','users','roles','audit-logs','dashboard','permissions'):
            self.assertEqual(self.client.get(f'/api/v1/admin/{resource}/').status_code, 403, resource)
        self.assertEqual(self.client.post('/api/v1/admin/brands/', {'code':'bad','name':'bad'}).status_code, 403)

    def test_login_csrf_session_rotation_logout_and_password_redaction(self):
        client = APIClient(enforce_csrf_checks=True)
        self.assertEqual(client.post('/api/v1/auth/login/', {'username':'root','password':PASSWORD}).status_code, 403)
        token = client.get('/api/v1/auth/csrf/').json()['csrfToken']
        result = client.post('/api/v1/auth/login/', {'username':'root','password':PASSWORD}, HTTP_X_CSRFTOKEN=token)
        self.assertEqual(result.status_code, 200)
        self.assertNotIn('password', result.json()['user'])
        self.assertTrue(client.cookies['sessionid']['httponly'])
        self.assertEqual(client.get('/api/v1/auth/session/').status_code, 200)
        self.assertEqual(client.post('/api/v1/admin/brands/', {'name':'Test','code':'test'}).status_code, 403)
        token = result.json()['csrfToken']
        self.assertEqual(client.post('/api/v1/admin/brands/', {'name':'Test','code':'test'}, HTTP_X_CSRFTOKEN=token).status_code, 201)
        self.assertEqual(client.delete('/api/v1/auth/session/', HTTP_X_CSRFTOKEN=token).status_code, 204)
        self.assertEqual(client.get('/api/v1/admin/brands/').status_code, 403)
        self.assertFalse(AuditLog.objects.filter(summary__contains=PASSWORD).exists())

    def test_inactive_and_nonstaff_accounts_cannot_login(self):
        User.objects.create_user('customer', password=PASSWORD)
        User.objects.create_user('disabled', password=PASSWORD, is_staff=True, is_active=False)
        for name in ('customer','disabled','missing'):
            self.assertEqual(self.client.post('/api/v1/auth/login/', {'username':name,'password':PASSWORD}).status_code, 400)

    def test_login_throttled(self):
        for _ in range(10):
            self.assertEqual(self.client.post('/api/v1/auth/login/', {'username':'missing','password':'wrong'}).status_code, 400)
        self.assertEqual(self.client.post('/api/v1/auth/login/', {'username':'missing','password':'wrong'}).status_code, 429)

    def test_reader_can_view_but_not_mutate(self):
        self.as_user(self.reader)
        brand = Brand.objects.first()
        self.assertEqual(self.client.get('/api/v1/admin/brands/').status_code, 200)
        self.assertEqual(self.client.post('/api/v1/admin/brands/', {'name':'Other','code':'other'}).status_code, 403)
        self.assertEqual(self.client.patch(f'/api/v1/admin/brands/{brand.pk}/', {'name':'Bad'}).status_code, 403)
        self.assertEqual(self.client.delete(f'/api/v1/admin/brands/{brand.pk}/').status_code, 403)
        self.assertEqual(self.client.get('/api/v1/admin/users/').status_code, 403)

    def test_staff_flag_alone_does_not_grant_model_reads_or_dashboard_counts(self):
        blank = User.objects.create_user('blank', password=PASSWORD, is_staff=True)
        self.as_user(blank)
        self.assertEqual(self.client.get('/api/v1/admin/graphics/').status_code, 403)
        self.assertEqual(self.client.get('/api/v1/admin/dashboard/').json()['counts'], {})

    def test_operator_crud_audit_search_pagination_and_active_filter(self):
        self.as_user(self.operator)
        result=self.client.post('/api/v1/admin/brands/', {'name':'Nokia','code':'nokia'}, format='json')
        self.assertEqual(result.status_code, 201)
        pk=result.json()['id']
        result=self.client.patch(f'/api/v1/admin/brands/{pk}/', {'active':False}, format='json')
        self.assertEqual(result.status_code, 200)
        filtered=self.client.get('/api/v1/admin/brands/?active=false&search=Nokia').json()
        self.assertEqual(filtered['count'], 1)
        self.assertEqual(self.client.delete(f'/api/v1/admin/brands/{pk}/').status_code, 204)
        self.assertEqual(list(AuditLog.objects.filter(object_id=str(pk),resource='management_api.brand').order_by('id').values_list('action',flat=True)),['create','update','delete'])
        listing=self.client.get('/api/v1/admin/graphics/').json()
        self.assertEqual(listing['count'], 24)
        self.assertEqual(len(listing['results']),20)
        self.assertIsNotNone(listing['next'])

    def test_protected_brand_and_legacy_codes_cannot_be_deleted_or_changed(self):
        self.as_user(self.root)
        brand=Brand.objects.get(code='apple')
        model=PhoneModel.objects.first()
        design=DesignTemplate.objects.first()
        self.assertEqual(self.client.delete(f'/api/v1/admin/brands/{brand.pk}/').status_code,409)
        for path,obj in [('phone-models',model),('designs',design)]:
            self.assertEqual(self.client.delete(f'/api/v1/admin/{path}/{obj.pk}/').status_code,400)
            self.assertEqual(self.client.patch(f'/api/v1/admin/{path}/{obj.pk}/', {'code':'changed'}).status_code,400)
        self.assertEqual(self.client.patch(f'/api/v1/admin/phone-models/{model.pk}/', {'name':'Different'}).status_code,400)
        self.client.patch(f'/api/v1/admin/phone-models/{model.pk}/', {'legacy_index':99})
        model.refresh_from_db()
        self.assertEqual(model.legacy_index,1)

    def test_role_and_account_changes_require_superuser_even_with_model_permissions(self):
        self.operator.user_permissions.add(*Permission.objects.filter(content_type__app_label='auth'))
        self.as_user(self.operator)
        self.assertEqual(self.client.get('/api/v1/admin/roles/').status_code,200)
        self.assertEqual(self.client.post('/api/v1/admin/roles/', {'name':'Escalation','permissions':[]}, format='json').status_code,403)
        self.assertEqual(self.client.patch(f'/api/v1/admin/users/{self.operator.pk}/', {'is_superuser':True}).status_code,403)

    def test_superuser_can_create_assign_disable_accounts_and_role_cannot_delete_with_members(self):
        self.as_user(self.root)
        permission=Permission.objects.get(codename='view_brand')
        role=self.client.post('/api/v1/admin/roles/', {'name':'Brand viewer','permissions':[permission.pk]},format='json').json()
        result=self.client.post('/api/v1/admin/users/', {'username':'newuser','password':PASSWORD,'is_staff':True,'groups':[role['id']]},format='json')
        self.assertEqual(result.status_code,201, result.data)
        self.assertNotIn('password',result.json())
        user=User.objects.get(username='newuser')
        self.assertTrue(user.check_password(PASSWORD))
        self.assertTrue(user.has_perm('management_api.view_brand'))
        self.assertFalse(user.has_perm('management_api.change_brand'))
        self.assertEqual(self.client.delete(f"/api/v1/admin/roles/{role['id']}/").status_code,400)
        self.assertEqual(self.client.patch(f'/api/v1/admin/users/{user.pk}/', {'is_active':False}).status_code,200)
        user.refresh_from_db();self.as_user(user)
        self.assertEqual(self.client.get('/api/v1/admin/brands/').status_code,403)

    def test_last_superuser_protected_and_weak_password_rejected(self):
        self.as_user(self.root)
        self.assertEqual(self.client.patch(f'/api/v1/admin/users/{self.root.pk}/', {'is_active':False}).status_code,400)
        self.assertEqual(self.client.delete(f'/api/v1/admin/users/{self.root.pk}/').status_code,405)
        self.assertEqual(self.client.post('/api/v1/admin/users/', {'username':'weak','password':'123456789012'}, format='json').status_code,400)

    def test_permission_revocation_applies_on_next_request(self):
        self.as_user(self.reader)
        self.assertEqual(self.client.get('/api/v1/admin/brands/').status_code,200)
        self.reader.groups.clear()
        self.assertEqual(self.client.get('/api/v1/admin/brands/').status_code,403)

    def test_own_password_change_verifies_old_password_and_keeps_session(self):
        self.as_user(self.reader)
        self.assertEqual(self.client.post('/api/v1/auth/password/', {'old_password':'wrong','new_password':'A-long-new-password!'}).status_code,400)
        self.assertEqual(self.client.post('/api/v1/auth/password/', {'old_password':PASSWORD,'new_password':'A-long-new-password!'}).status_code,200)
        self.assertEqual(self.client.get('/api/v1/auth/session/').status_code,200)
        self.reader.refresh_from_db();self.assertTrue(self.reader.check_password('A-long-new-password!'))

    def test_audit_cannot_be_modified_even_by_superuser(self):
        self.as_user(self.root)
        log=AuditLog.objects.create(actor_name='system',action='test',resource='test')
        self.assertEqual(self.client.patch(f'/api/v1/admin/audit-logs/{log.pk}/',{'summary':'tamper'}).status_code,405)
        self.assertEqual(self.client.delete(f'/api/v1/admin/audit-logs/{log.pk}/').status_code,405)

    def test_orders_empty_by_default_and_support_can_only_update_notes(self):
        self.assertEqual(PrintOrder.objects.count(),0)
        order=PrintOrder.objects.create(model_name='iPhone 16',amount='10.00')
        self.as_user(self.support)
        path=f'/api/v1/admin/orders/{order.pk}/'
        self.assertEqual(self.client.get(path).status_code,200)
        self.assertEqual(self.client.patch(path,{'notes':'Customer called'}).status_code,200)
        self.assertEqual(self.client.patch(path,{'status':'paid'}).status_code,400)
        self.assertEqual(self.client.post('/api/v1/admin/orders/',{}).status_code,403)
        self.assertEqual(self.client.get('/api/v1/admin/users/').status_code,403)
        counts=self.client.get('/api/v1/admin/dashboard/').json()['counts']
        self.assertIn('orders',counts);self.assertNotIn('graphics',counts)
        self.as_user(self.root)
        self.assertEqual(self.client.post('/api/v1/admin/orders/',{}).status_code,405)

    def test_plan_validation_and_public_catalog_filters(self):
        self.as_user(self.root)
        plan=PricingPlan.objects.get(code='ai-monthly')
        self.assertEqual(self.client.patch(f'/api/v1/admin/plans/{plan.pk}/',{'price':'-1'}).status_code,400)
        self.assertEqual(self.client.patch(f'/api/v1/admin/plans/{plan.pk}/',{'monthly_credits':0}).status_code,400)
        Brand.objects.filter(code='apple').update(active=False)
        AIStyle.objects.update(prompt='Private prompt')
        self.client.logout()
        result=self.client.get('/api/v1/catalog/').json()
        self.assertEqual(len(result['phone_models']),1)
        self.assertNotIn('prompt',result['ai_styles'][0])
        self.assertEqual(result['plans'][1]['price'],'9.90')

    def test_seed_is_idempotent_and_keeps_manual_config_and_grants(self):
        PricingPlan.objects.filter(code='ai-monthly').update(price='11.90')
        group=Group.objects.get(name='只读人员');group.permissions.clear()
        call_command('seed_catalog',stdout=StringIO())
        self.assertEqual(Graphic.objects.count(),24)
        self.assertEqual(DesignTemplate.objects.count(),6)
        self.assertEqual(str(PricingPlan.objects.get(code='ai-monthly').price),'11.90')
        self.assertEqual(group.permissions.count(),0)

    def test_asset_upload_validates_permission_content_and_reencodes(self):
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            stream=BytesIO();Image.new('RGB',(10,10),'red').save(stream,format='JPEG')
            content=stream.getvalue()
            self.as_user(self.reader)
            result=self.client.post('/api/v1/admin/uploads/',{'file':SimpleUploadedFile('test.jpg',content,content_type='image/jpeg')})
            self.assertEqual(result.status_code,403)
            self.as_user(self.operator)
            self.assertEqual(self.client.post('/api/v1/admin/uploads/',{'file':SimpleUploadedFile('bad.png',b'<script>bad</script>',content_type='image/png')}).status_code,400)
            self.assertEqual(self.client.post('/api/v1/admin/uploads/',{'file':SimpleUploadedFile('bad.svg',b'<svg/>',content_type='image/svg+xml')}).status_code,400)
            result=self.client.post('/api/v1/admin/uploads/',{'file':SimpleUploadedFile('test.jpg',content,content_type='image/jpeg')})
            self.assertEqual(result.status_code,201,result.data)
            self.assertRegex(result.json()['path'],r'^/media/uploads/[0-9a-f]{32}\.png$')
            image_path=result.json()['path']
            self.assertEqual(self.client.post('/api/v1/admin/graphics/',{'name':'Uploaded','code':'uploaded','image_path':image_path}).status_code,201)
            self.assertEqual(self.client.post('/api/v1/admin/graphics/',{'name':'Bad','code':'bad','image_path':'javascript:alert(1)'}).status_code,400)
            self.assertEqual(self.client.post('/api/v1/admin/graphics/',{'name':'Bad','code':'bad','image_path':'/assets/../../secret.png'}).status_code,400)

    def test_ai_example_crud_nested_results_validation_and_audit(self):
        from .models import AIExample
        self.as_user(self.operator)
        style = AIStyle.objects.get(code='anime')
        payload = {'code':'new-case','name':'New case','subject':'One photo, many looks','original_path':'/assets/ai-styles/original.png','results':[{'style':style.pk,'image_path':'/assets/ai-styles/anime.png'}]}
        result = self.client.post('/api/v1/admin/ai-examples/', payload, format='json')
        self.assertEqual(result.status_code, 201, result.data)
        path = f"/api/v1/admin/ai-examples/{result.data['id']}/"
        self.assertEqual(result.data['results'][0]['style_code'], 'anime')
        self.assertEqual(self.client.patch(path, {'subject':'Edited'}, format='json').status_code, 200)
        example = AIExample.objects.get(code='new-case')
        self.assertEqual(example.results.count(), 1)
        for patch in ({'results':[]}, {'results':payload['results']*2}, {'original_path':'https://other.test/pic.png'}, {'results':[{'style':style.pk,'image_path':'/assets/../secret.png'}]}):
            self.assertEqual(self.client.patch(path, patch, format='json').status_code, 400)
            self.assertEqual(example.results.count(), 1)
        self.assertEqual(self.client.delete(f'/api/v1/admin/ai-styles/{style.pk}/').status_code, 409)
        self.assertEqual(self.client.delete(path).status_code, 204)
        self.assertEqual(list(AuditLog.objects.filter(resource='management_api.aiexample',object_id=str(example.pk)).order_by('id').values_list('action',flat=True)), ['create','update','delete'])

    def test_public_ai_cases_have_three_results_and_filter_inactive_cases_and_styles(self):
        from .models import AIExample
        data = self.client.get('/api/v1/catalog/').json()
        self.assertEqual(data['version'], 2)
        self.assertEqual(len(data['ai_examples']), 4)
        self.assertTrue(all(len(e['results']) == 3 for e in data['ai_examples']))
        AIStyle.objects.filter(code='anime').update(active=False, prompt='private')
        AIExample.objects.filter(code='pets').update(active=False)
        response = self.client.get('/api/v1/catalog/')
        self.assertIn('no-store', response['Cache-Control'])
        data = response.json()
        self.assertEqual(len(data['ai_examples']), 3)
        self.assertTrue(all(len(e['results']) == 2 for e in data['ai_examples']))
        self.assertNotIn('private', str(data))
        AIStyle.objects.update(active=False)
        self.assertEqual(self.client.get('/api/v1/catalog/').json()['ai_examples'], [])

    def test_ai_case_permissions_apply_to_reads_writes_and_uploads(self):
        from .models import AIExample
        path = f'/api/v1/admin/ai-examples/{AIExample.objects.first().pk}/'
        self.assertEqual(self.client.get(path).status_code, 403)
        self.as_user(self.reader)
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.patch(path, {'subject':'Denied'}).status_code, 403)
        self.as_user(self.support)
        self.assertEqual(self.client.get(path).status_code, 403)
        editor = User.objects.create_user('case-editor', password=PASSWORD, is_staff=True)
        editor.user_permissions.add(Permission.objects.get(codename='change_aiexample'))
        self.as_user(editor)
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            stream=BytesIO();Image.new('RGB',(10,10),'blue').save(stream,format='PNG')
            self.assertEqual(self.client.post('/api/v1/admin/uploads/',{'file':SimpleUploadedFile('case.png',stream.getvalue(),content_type='image/png')}).status_code, 201)

    def test_single_active_plan_and_config_survives_seeding(self):
        self.as_user(self.root)
        plan = PricingPlan.objects.get(kind='print')
        self.assertEqual(self.client.patch(f'/api/v1/admin/plans/{plan.pk}/', {'price':'9.90'}).status_code, 200)
        ai = PricingPlan.objects.get(kind='ai_monthly')
        self.assertEqual(self.client.patch(f'/api/v1/admin/plans/{ai.pk}/', {'price':'5.99','monthly_credits':15,'trial_credits':3}).status_code, 200)
        payload = {'code':'second-print','name':'Second','kind':'print','price':'8.00'}
        self.assertEqual(self.client.post('/api/v1/admin/plans/', payload).status_code, 400)
        payload['active'] = False
        result = self.client.post('/api/v1/admin/plans/', payload)
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(self.client.patch(f"/api/v1/admin/plans/{result.data['id']}/", {'active':True}).status_code, 400)
        call_command('seed_catalog', stdout=StringIO())
        data = self.client.get('/api/v1/catalog/').json()['plans']
        self.assertEqual([(p['price'],p['monthly_credits'],p['trial_credits']) for p in data], [('9.90',0,0),('5.99',15,3)])

    def test_case_seed_preserves_managed_images_removed_effects_and_existing_permissions(self):
        from .models import AIExample
        example = AIExample.objects.get(code='pets')
        example.original_path = '/media/uploads/custom.png';example.save()
        example.results.filter(style__code='anime').delete()
        Group.objects.get(name='运营管理员').permissions.clear()
        call_command('seed_catalog', stdout=StringIO())
        example.refresh_from_db()
        self.assertEqual(example.original_path, '/media/uploads/custom.png')
        self.assertEqual(example.results.count(), 2)
        self.assertEqual(AIExample.objects.count(), 4)
        self.assertEqual(Group.objects.get(name='运营管理员').permissions.count(), 0)
