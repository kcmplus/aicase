import hashlib
import re
import time
from datetime import timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

import jwt
import requests
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import rsa
from django.contrib.auth.models import User
from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .ai_service import cipher
from .customer_auth import complete_customer_login
from .models import Customer, CustomerSocialIdentity, SocialLoginAttempt, SocialLoginConfig, AIAccount, CreditEntry, SMTPConfig, AuditLog
from .social_login import exchange_identity


@override_settings(AI_CONFIG_ENCRYPTION_KEY=Fernet.generate_key().decode())
class SocialLoginTests(TestCase):
    def setUp(self):
        self.client=APIClient()
        self.admin=User.objects.create_superuser('social-admin','admin@example.com','test-admin-only')
        self.config=SocialLoginConfig.objects.create(provider='google',enabled=True,client_id='123.apps.googleusercontent.com',site_origin='https://aicase.chunpat.cc',secret_ciphertext=cipher().encrypt(b'secret-canary').decode())
        SMTPConfig.objects.create(signup_credits=5,enabled=True,host='smtp.example.com',from_email='sender@example.com')
        self.identity={'subject':'subject-1','email':'person@gmail.com','name':'Tester','trusted':True}

    def start(self,provider='google',client=None):
        client=client or self.client
        response=client.post(f'/api/v1/store/customer/social/{provider}/start/',{'device_id':'789','shop_id':'351','next':'ai','language':'zh-CN'},format='json')
        self.assertEqual(response.status_code,200,response.data)
        params=parse_qs(urlsplit(response.data['authorizationUrl']).query)
        state=params['state'][0]
        return state,params

    def callback(self,state,provider='google',client=None,identity=None,**query):
        with patch('management_api.social_login.exchange_identity',return_value=identity or self.identity) as exchange:
            response=(client or self.client).get(f'/api/v1/store/customer/social/{provider}/callback/',{'state':state,'code':'code-canary',**query})
        return response,exchange

    def facebook(self):
        return SocialLoginConfig.objects.create(provider='facebook',enabled=True,client_id='12345',site_origin=self.config.site_origin,secret_ciphertext=self.config.secret_ciphertext)

    def test_config_superuser_only_encrypted_revision_and_no_secret_echo(self):
        url='/api/v1/admin/social-login/google/'
        self.assertEqual(self.client.get(url).status_code,403)
        staff=User.objects.create_user('staff',is_staff=True)
        self.client.force_authenticate(staff);self.assertEqual(self.client.get(url).status_code,403)
        self.client.force_authenticate(self.admin)
        public=self.client.get(url).data
        self.assertTrue(public['has_secret']);self.assertNotIn('secret-canary',str(public));self.assertNotIn('secret_ciphertext',public)
        body={'revision':0,'enabled':True,'client_id':self.config.client_id,'site_origin':self.config.site_origin,'secret':'new-secret-canary'}
        result=self.client.patch(url,body,format='json');self.assertEqual(result.status_code,200,result.data)
        self.config.refresh_from_db();self.assertNotEqual(self.config.secret_ciphertext,'new-secret-canary')
        self.assertEqual(cipher().decrypt(self.config.secret_ciphertext.encode()),b'new-secret-canary')
        self.assertNotIn('new-secret-canary',str(result.data));self.assertNotIn('new-secret-canary',str(list(AuditLog.objects.values())))
        self.assertEqual(self.client.patch(url,body,format='json').status_code,409)
        body.update(revision=1,secret='',clear_secret=True)
        self.assertEqual(self.client.patch(url,body,format='json').status_code,400)
        body.update(clear_secret=False,site_origin='https://example.com/path')
        self.assertEqual(self.client.patch(url,body,format='json').status_code,400)

    def test_admin_and_guest_start_require_csrf(self):
        client=APIClient(enforce_csrf_checks=True)
        self.assertEqual(client.post('/api/v1/store/customer/social/google/start/',{}).status_code,403)
        client.force_login(self.admin)
        self.assertEqual(client.patch('/api/v1/admin/social-login/google/',{},format='json').status_code,403)

    def test_disabled_hidden_and_start_blocked(self):
        self.config.enabled=False;self.config.save()
        self.assertEqual(self.client.get('/api/v1/store/customer/').data['socialProviders'],[])
        self.assertEqual(self.client.post('/api/v1/store/customer/social/google/start/',{},format='json').status_code,503)
        self.assertFalse(SocialLoginAttempt.objects.exists())

    def test_authorization_has_pkce_nonce_fixed_callback_and_hashed_state(self):
        state,params=self.start()
        attempt=SocialLoginAttempt.objects.get()
        self.assertEqual(attempt.pk,hashlib.sha256(state.encode()).hexdigest())
        self.assertNotEqual(attempt.browser_hash,self.client.session['social_browser'])
        self.assertEqual(params['code_challenge_method'],['S256']);self.assertEqual(params['nonce'],[attempt.nonce])
        self.assertEqual(params['redirect_uri'],[self.config.site_origin+'/api/v1/store/customer/social/google/callback/'])
        self.assertNotIn('secret-canary',str(params))

    def test_new_google_customer_session_and_single_gift_across_logins(self):
        state,_=self.start();response,_=self.callback(state)
        self.assertIn('social=success',response.url);self.assertIn('device_id=789',response.url);self.assertIn('next=ai',response.url)
        self.assertEqual(response['Referrer-Policy'],'no-referrer');self.assertIn('no-store',response['Cache-Control'])
        self.assertEqual(self.client.get('/api/v1/store/customer/').data['customer']['email'],'person@gmail.com')
        self.assertEqual(AIAccount.objects.get().trial_granted,5);self.assertEqual(CreditEntry.objects.filter(kind='signup').count(),1)
        self.client.delete('/api/v1/store/customer/')
        state,_=self.start();response,_=self.callback(state)
        self.assertIn('social=success',response.url);self.assertEqual(Customer.objects.count(),1);self.assertEqual(CreditEntry.objects.filter(kind='signup').count(),1)

    def test_existing_verified_email_keeps_credits_and_no_duplicate_account(self):
        with transaction.atomic():customer,_=complete_customer_login(email='person@gmail.com')
        AIAccount.objects.update(trial_used=2)
        state,_=self.start();response,_=self.callback(state)
        self.assertIn('social=success',response.url);self.assertEqual(Customer.objects.count(),1)
        self.assertEqual(CustomerSocialIdentity.objects.get().customer,customer);self.assertEqual(AIAccount.objects.get().trial_used,2)

    def test_disabled_customer_cannot_login_or_receive_gift(self):
        Customer.objects.create(email='person@gmail.com',verified_at=timezone.now(),active=False)
        state,_=self.start();response,_=self.callback(state)
        self.assertIn('social=failed',response.url);self.assertFalse(AIAccount.objects.exists());self.assertNotIn('store_customer_id',self.client.session)

    def test_wrong_browser_provider_and_replay_never_exchange(self):
        self.facebook();state,_=self.start()
        response,exchange=self.callback(state,client=APIClient());self.assertIn('social=failed',response.url);exchange.assert_not_called()
        response,exchange=self.callback(state,provider='facebook');self.assertIn('social=failed',response.url);exchange.assert_not_called()
        response,exchange=self.callback(state);self.assertIn('social=success',response.url);exchange.assert_called_once()
        response,exchange=self.callback(state);self.assertIn('social=failed',response.url);exchange.assert_not_called()

    def test_expired_state_changed_configuration_and_new_start_invalidate_old_flow(self):
        state,_=self.start();SocialLoginAttempt.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
        _,exchange=self.callback(state);exchange.assert_not_called()
        state,_=self.start();self.config.revision+=1;self.config.save()
        _,exchange=self.callback(state);exchange.assert_not_called()
        state,_=self.start();self.start()
        _,exchange=self.callback(state);exchange.assert_not_called()

    def test_cancel_and_timeout_are_safe_and_do_not_replay_code(self):
        state,_=self.start();response,exchange=self.callback(state,error='access_denied',error_description='private')
        self.assertIn('social=cancelled',response.url);self.assertNotIn('private',response.url);exchange.assert_not_called()
        state,_=self.start()
        with patch('management_api.social_login.exchange_identity',side_effect=requests.Timeout('secret-canary')):
            response=self.client.get('/api/v1/store/customer/social/google/callback/',{'state':state,'code':'code-canary'})
        self.assertIn('social=failed',response.url);self.assertNotIn('canary',response.url)
        _,exchange=self.callback(state);exchange.assert_not_called();self.assertFalse(Customer.objects.exists())

    def test_facebook_first_login_requires_mailbox_proof_and_later_uses_subject(self):
        self.facebook()
        state, params = self.start('facebook')
        self.assertEqual(params['scope'], ['public_profile'])
        email = 'existing@example.com'
        fb = {**self.identity, 'email': '', 'trusted': False}
        with transaction.atomic():
            customer, _ = complete_customer_login(email=email)
        response,_=self.callback(state,'facebook',identity=fb)
        self.assertIn('social=verify_email',response.url);self.assertNotIn('store_customer_id',self.client.session)
        self.assertFalse(CustomerSocialIdentity.objects.exists());self.assertEqual(Customer.objects.count(),1)
        pending = self.client.get('/api/v1/store/customer/').data['socialPending']
        self.assertEqual(pending, {'provider': 'facebook', 'email': ''})
        with patch('management_api.customer_auth.send_transactional_mail') as mail:
            result=self.client.post('/api/v1/store/customer/send-code/',{'email':email},format='json')
        self.assertEqual(result.status_code,200)
        code=re.search(r'\b\d{6}\b',mail.call_args.args[2])[0]
        result=self.client.post('/api/v1/store/customer/verify/',{'email':email,'code':code},format='json')
        self.assertEqual(result.status_code,200,result.data);self.assertEqual(CustomerSocialIdentity.objects.get().customer,customer)
        self.assertEqual(CreditEntry.objects.filter(kind='signup').count(),1)
        self.client.delete('/api/v1/store/customer/');state,_=self.start('facebook')
        response,_=self.callback(state,'facebook',identity=fb)
        self.assertIn('social=success',response.url);self.assertEqual(self.client.get('/api/v1/store/customer/').data['customer']['email'],email)

    def test_external_google_email_uses_verification_and_missing_email_is_supported(self):
        state,_=self.start();response,_=self.callback(state,identity={**self.identity,'trusted':False,'email':''})
        self.assertIn('social=verify_email',response.url);self.assertFalse(Customer.objects.exists())
        self.assertEqual(self.client.get('/api/v1/store/customer/').data['socialPending']['email'],'')
        self.client.delete('/api/v1/store/customer/');self.assertIsNone(self.client.get('/api/v1/store/customer/').data['socialPending'])

    def test_google_signed_token_audience_issuer_expiry_nonce_and_authority(self):
        self.start();attempt=SocialLoginAttempt.objects.get()
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        claims={'iss':'https://accounts.google.com','aud':self.config.client_id,'sub':'subject','iat':int(time.time())-1,'exp':int(time.time())+600,'nonce':attempt.nonce,'email':'person@gmail.com','email_verified':True}
        def verify(changes):
            token=jwt.encode({**claims,**changes},key,algorithm='RS256',headers={'kid':'test-key'})
            with patch('management_api.social_login.provider_json',return_value={'id_token':token}),patch('management_api.social_login.GOOGLE_KEYS.get_signing_key_from_jwt',return_value=SimpleNamespace(key=key.public_key())):
                return exchange_identity(self.config,attempt,'code')
        self.assertTrue(verify({})['trusted'])
        self.assertFalse(verify({'email':'person@example.com'})['trusted'])
        self.assertFalse(verify({'email_verified':False})['trusted'])
        for change in [{'aud':'other'},{'iss':'https://attacker.example'},{'exp':int(time.time())-5},{'nonce':'wrong'},{'azp':'other'}]:
            with self.subTest(change=change),self.assertRaises((ValueError,jwt.PyJWTError)):verify(change)

    def test_facebook_checks_token_application_user_and_expiry(self):
        c=self.facebook();self.start('facebook');attempt=SocialLoginAttempt.objects.get()
        good={'data':{'is_valid':True,'app_id':'12345','user_id':'u1','type':'USER','expires_at':int(time.time())+600}}
        for changed in [None,{'app_id':'other'},{'user_id':'other'},{'expires_at':1},{'is_valid':False}]:
            checked=good if not changed else {'data':{**good['data'],**changed}}
            with patch('management_api.social_login.provider_json',side_effect=[{'access_token':'token-canary'},checked,{'id':'u1','name':'Tester'}]) as fetch:
                if changed:
                    with self.assertRaises(ValueError):exchange_identity(c,attempt,'code')
                else:
                    identity = exchange_identity(c, attempt, 'code')
                    self.assertFalse(identity['trusted'])
                    self.assertEqual(identity['email'], '')
                    self.assertEqual(fetch.call_args.kwargs['params']['fields'], 'id,name')
                    self.assertIn('appsecret_proof',fetch.call_args.kwargs['params'])
                    self.assertEqual(fetch.call_args.kwargs['headers']['Authorization'],'Bearer token-canary')

    def test_google_rejects_forged_signature(self):
        self.start();attempt=SocialLoginAttempt.objects.get()
        attacker=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        trusted=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        claims={'iss':'https://accounts.google.com','aud':self.config.client_id,'sub':'victim','iat':int(time.time()),'exp':int(time.time())+600,'nonce':attempt.nonce,'email':'victim@gmail.com','email_verified':True}
        token=jwt.encode(claims,attacker,algorithm='RS256')
        with patch('management_api.social_login.provider_json',return_value={'id_token':token}),patch('management_api.social_login.GOOGLE_KEYS.get_signing_key_from_jwt',return_value=SimpleNamespace(key=trusted.public_key())):
            with self.assertRaises(jwt.InvalidSignatureError):exchange_identity(self.config,attempt,'code')
        self.assertFalse(Customer.objects.exists())

    def test_configuration_disabled_during_exchange_prevents_login(self):
        state,_=self.start()
        def exchange(*args):
            SocialLoginConfig.objects.filter(pk='google').update(enabled=False,revision=1)
            return self.identity
        with patch('management_api.social_login.exchange_identity',side_effect=exchange):
            response=self.client.get('/api/v1/store/customer/social/google/callback/',{'state':state,'code':'code'})
        self.assertIn('social=failed',response.url);self.assertFalse(Customer.objects.exists())

    def test_pending_identity_expires_or_configuration_change_discards_binding(self):
        for expired in [True,False]:
            state,_=self.start();self.callback(state,identity={**self.identity,'trusted':False})
            session=self.client.session
            if expired:
                session['social_pending']={**session['social_pending'],'expires_at':time.time()-1};session.save()
            else:
                SocialLoginConfig.objects.filter(pk='google').update(revision=1)
            self.assertIsNone(self.client.get('/api/v1/store/customer/').data['socialPending'])
            self.assertFalse(CustomerSocialIdentity.objects.exists())

    def test_existing_identity_cannot_be_replaced_via_matching_email(self):
        with transaction.atomic():customer,_=complete_customer_login(email=self.identity['email'])
        CustomerSocialIdentity.objects.create(customer=customer,provider='google',client_id=self.config.client_id,subject='original-subject')
        state,_=self.start();response,_=self.callback(state)
        self.assertIn('social=failed',response.url)
        self.assertNotIn('store_customer_id',self.client.session)
        self.assertEqual(CustomerSocialIdentity.objects.get().subject,'original-subject')
        self.assertEqual(CreditEntry.objects.filter(kind='signup').count(),1)
