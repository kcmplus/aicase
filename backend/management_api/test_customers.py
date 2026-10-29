import hashlib
from datetime import timedelta
from django.contrib.auth.models import User, Permission
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from .models import Customer, AIAccount, EmailChallenge, AuditLog
from .customer_auth import code_digest


class CustomerManagementTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('manager', password='test-only-password')
        self.staff = User.objects.create_user('support', password='test-only-password', is_staff=True)
        self.customer = Customer.objects.create(email='person@example.com', display_name='Jane', verified_at=timezone.now())
        self.account = AIAccount.objects.create(customer=self.customer, owner_hash=hashlib.sha256(('customer:'+str(self.customer.pk)).encode()).hexdigest(), trial_granted=3, trial_used=2)
        self.admin_client = APIClient();self.admin_client.force_authenticate(self.admin)
        self.client = APIClient()
        session = self.client.session;session['store_customer_id'] = str(self.customer.pk);session.save()
        self.url = f'/api/v1/admin/customers/{self.customer.pk}/'

    def test_directory_is_paginated_searchable_and_permission_protected(self):
        self.assertEqual(self.client.get('/api/v1/admin/customers/').status_code,403)
        staff = APIClient();staff.force_authenticate(self.staff)
        self.assertEqual(staff.get('/api/v1/admin/customers/').status_code,403)
        self.staff.user_permissions.add(Permission.objects.get(codename='view_customer'))
        staff.force_authenticate(User.objects.get(pk=self.staff.pk))
        self.assertEqual(staff.get('/api/v1/admin/customers/').status_code,200)
        self.assertEqual(staff.patch(self.url, {'revision':0,'active':False},format='json').status_code,403)
        self.staff.user_permissions.add(Permission.objects.get(codename='change_customer'))
        staff.force_authenticate(User.objects.get(pk=self.staff.pk))
        self.assertEqual(staff.patch(self.url, {'revision':0,'notes':'Handled'},format='json').status_code,200)
        self.assertEqual(staff.post(self.url+'grant/', {'revision':1,'amount':3,'reason':'Support'},format='json').status_code,403)
        for n in range(23):Customer.objects.create(email=f'other{n}@example.com',active=False,verified_at=timezone.now())
        listing=self.admin_client.get('/api/v1/admin/customers/').data
        self.assertEqual(listing['count'],24);self.assertEqual(len(listing['results']),20);self.assertIsNotNone(listing['next'])
        self.assertEqual(self.admin_client.get('/api/v1/admin/customers/?search=jane').data['count'],1)
        self.assertEqual(self.admin_client.get('/api/v1/admin/customers/?active=false').data['count'],23)
        detail=self.admin_client.get(self.url).data
        self.assertEqual(detail['credits']['remaining'],1)
        for hidden in ['owner_hash','session_version','password','input_image','code_hash']:
            self.assertNotIn(hidden,str(detail))

    def test_disable_revokes_old_session_even_after_reenable(self):
        self.assertTrue(self.client.get('/api/v1/store/ai-account/').data['authenticated'])
        result=self.admin_client.patch(self.url,{'revision':0,'active':False},format='json')
        self.assertEqual(result.status_code,200)
        self.assertFalse(self.client.get('/api/v1/store/ai-account/').data['authenticated'])
        self.assertEqual(self.admin_client.patch(self.url,{'revision':1,'active':True},format='json').status_code,200)
        self.assertFalse(self.client.get('/api/v1/store/ai-account/').data['authenticated'])
        now=timezone.now()
        challenge=EmailChallenge(email=self.customer.email,expires_at=now+timedelta(minutes=10),sent_at=now,window_at=now,delivered=True)
        challenge.code_hash=code_digest(challenge.email,challenge.nonce,'123456');challenge.save()
        result=self.client.post('/api/v1/store/customer/verify/',{'email':self.customer.email,'code':'123456'},format='json')
        self.assertEqual(result.status_code,200)
        self.assertTrue(self.client.get('/api/v1/store/ai-account/').data['authenticated'])
        self.customer.refresh_from_db();self.assertIsNotNone(self.customer.last_login_at)
        self.account.refresh_from_db();self.assertEqual(self.account.trial_used,2)

    def test_profile_updates_only_name_without_exposing_notes_or_staff_privileges(self):
        self.customer.notes='Private support note';self.customer.save()
        result=self.client.patch('/api/v1/store/customer/',{'displayName':'  My name  '},format='json')
        self.assertEqual(result.status_code,200);self.assertEqual(result.data['customer']['displayName'],'My name')
        self.assertNotIn('Private support note',str(result.data))
        self.assertEqual(self.client.patch('/api/v1/store/customer/',{'displayName':'Hi','active':True},format='json').status_code,400)
        self.assertEqual(self.client.patch('/api/v1/store/customer/',{'email':'new@example.com'},format='json').status_code,400)
        strict=APIClient(enforce_csrf_checks=True);strict.cookies=self.client.cookies
        self.assertEqual(strict.patch('/api/v1/store/customer/',{'displayName':'Hi'},format='json').status_code,403)
        self.assertEqual(self.admin_client.patch(self.url,{'revision':0,'notes':'stale'},format='json').status_code,409)
        self.assertEqual(self.client.get('/api/v1/auth/session/').status_code,403)

    def test_grant_is_additive_audited_and_not_repeated_on_retry(self):
        body={'revision':0,'amount':4,'reason':'Customer support compensation'}
        result=self.admin_client.post(self.url+'grant/',body,format='json')
        self.assertEqual(result.status_code,200,result.data)
        self.assertEqual(result.data['credits'],{'welcome_granted':3,'bonus_granted':4,'used':2,'remaining':5})
        self.assertEqual(self.admin_client.post(self.url+'grant/',body,format='json').status_code,409)
        self.assertEqual(self.client.get('/api/v1/store/ai-account/').data['trialRemaining'],5)
        entry=AuditLog.objects.get(object_id=str(self.customer.pk));self.assertIn('4',entry.summary);self.assertIn(body['reason'],entry.summary)
        for amount in [0,-1,1001,1.5]:self.assertEqual(self.admin_client.post(self.url+'grant/',{**body,'revision':1,'amount':amount},format='json').status_code,400)
        self.assertEqual(self.admin_client.post(self.url+'grant/',{**body,'revision':1,'reason':''},format='json').status_code,400)
        self.assertEqual(self.admin_client.patch(self.url,{'revision':1,'email':'other@example.com'},format='json').status_code,400)
        self.assertEqual(self.admin_client.delete(self.url).status_code,405)
        self.assertEqual(self.admin_client.post('/api/v1/admin/customers/',{'email':'other@example.com'},format='json').status_code,405)
        self.admin_client.patch(self.url,{'revision':1,'active':False},format='json')
        self.assertEqual(self.admin_client.post(self.url+'grant/',{**body,'revision':2},format='json').status_code,400)
