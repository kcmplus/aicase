import hashlib
import re
from datetime import timedelta
from unittest.mock import patch
from io import StringIO

from cryptography.fernet import Fernet
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from .models import AIAccount, Customer, EmailChallenge, SMTPConfig, PricingPlan
from .ai_service import cipher


@override_settings(AI_CONFIG_ENCRYPTION_KEY=Fernet.generate_key().decode())
class CustomerAccountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_catalog',stdout=StringIO())
        PricingPlan.objects.filter(kind='ai_monthly').update(trial_credits=3)
        SMTPConfig.objects.create(signup_credits=3,enabled=True,host='smtp.example.com',from_email='hello@example.com')

    def setUp(self):
        cache.clear()
        self.client=APIClient()

    def send(self,email='person@example.com',client=None):
        with patch('management_api.customer_auth.send_transactional_mail') as mail:
            result=(client or self.client).post('/api/v1/store/customer/send-code/',{'email':email},format='json')
        self.assertEqual(result.status_code,200,result.data)
        code=re.search(r'\b\d{6}\b',mail.call_args.args[2])[0]
        self.assertNotIn(code,str(result.data))
        self.assertIn(code,mail.call_args.kwargs['html_body'])
        self.assertIn('Expires in 10 minutes',mail.call_args.kwargs['html_body'])
        return code

    def verify(self,code,email='person@example.com',client=None):
        return (client or self.client).post('/api/v1/store/customer/verify/',{'email':email,'code':code},format='json')

    def test_signup_requires_verified_email_and_gift_is_once_across_browsers(self):
        guest=self.client.get('/api/v1/store/ai-account/').data
        self.assertFalse(guest['authenticated']);self.assertEqual(guest['trialRemaining'],0)
        self.assertEqual(guest['signupCredits'],3);self.assertFalse(AIAccount.objects.exists())
        code=self.send('Person@Example.com')
        self.assertFalse(Customer.objects.exists())
        self.assertNotIn(code,EmailChallenge.objects.get().code_hash)
        first=self.verify(code);self.assertEqual(first.status_code,200,first.data)
        self.assertEqual(Customer.objects.get().email,'person@example.com')
        self.assertEqual(AIAccount.objects.get().trial_granted,3)
        AIAccount.objects.update(trial_used=2)
        SMTPConfig.objects.update(signup_credits=10)
        EmailChallenge.objects.update(sent_at=timezone.now()-timedelta(minutes=2))
        other=APIClient();code=self.send(client=other)
        second=self.verify(code,client=other);self.assertFalse(second.data['created'])
        data=other.get('/api/v1/store/ai-account/').data
        self.assertEqual(data['trialRemaining'],1);self.assertEqual(data['trialGranted'],3)
        self.assertEqual(Customer.objects.count(),1);self.assertEqual(AIAccount.objects.count(),1)
        self.assertEqual(self.verify(code).status_code,400)  # replay

    def test_signup_offer_independent_from_plan_and_zero_is_respected(self):
        PricingPlan.objects.filter(kind='ai_monthly').update(trial_credits=99)
        self.assertEqual(self.client.get('/api/v1/store/customer/').data['signupCredits'], 3)
        self.assertEqual(self.client.get('/api/v1/catalog/').data['signupCredits'], 3)
        self.verify(self.send())
        SMTPConfig.objects.update(signup_credits=0)
        self.verify(self.send('second@example.com'), 'second@example.com')
        self.assertEqual(AIAccount.objects.get(customer__email='second@example.com').trial_granted, 0)
        self.assertEqual(AIAccount.objects.get(customer__email='person@example.com').trial_granted, 3)

    def test_code_expiry_attempt_limit_and_resend_invalidation(self):
        code=self.send()
        wrong='000001' if code=='000000' else '000000'
        for _ in range(5):self.assertEqual(self.verify(wrong).status_code,400)
        self.assertEqual(self.verify(code).status_code,400)
        EmailChallenge.objects.update(sent_at=timezone.now()-timedelta(minutes=2))
        new=self.send()
        EmailChallenge.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.verify(new).status_code,400)
        self.assertFalse(Customer.objects.exists())

    def test_resend_and_mail_failure_do_not_grant_or_expose_code(self):
        self.send()
        with patch('management_api.customer_auth.send_transactional_mail') as mail:
            response=self.client.post('/api/v1/store/customer/send-code/',{'email':'person@example.com'},format='json')
            self.assertEqual(response.status_code,429);mail.assert_not_called()
        EmailChallenge.objects.update(sent_at=timezone.now()-timedelta(minutes=2))
        with patch('management_api.customer_auth.send_transactional_mail',side_effect=Exception('secret-smtp-password')):
            response=self.client.post('/api/v1/store/customer/send-code/',{'email':'person@example.com'},format='json')
        self.assertEqual(response.status_code,503);self.assertNotIn('secret-smtp',str(response.data))
        self.assertFalse(EmailChallenge.objects.get().delivered);self.assertFalse(AIAccount.objects.exists())

    def test_browser_key_cannot_claim_credit_and_logout_revokes_access(self):
        self.client.credentials(HTTP_X_ORDER_KEY='a'*64)
        self.assertEqual(self.client.post('/api/v1/store/ai-renders/',{},format='json').status_code,403)
        self.verify(self.send())
        self.assertTrue(self.client.get('/api/v1/store/ai-account/').data['authenticated'])
        self.assertEqual(self.client.delete('/api/v1/store/customer/').status_code,200)
        self.assertFalse(self.client.get('/api/v1/store/ai-account/').data['authenticated'])
        self.assertEqual(AIAccount.objects.get().trial_granted,3)

    def test_customer_does_not_gain_admin_access_and_csrf_is_required(self):
        self.verify(self.send())
        self.assertEqual(self.client.get('/api/v1/admin/mail/').status_code,403)
        strict=APIClient(enforce_csrf_checks=True)
        self.assertEqual(strict.post('/api/v1/store/customer/send-code/',{'email':'a@example.com'},format='json').status_code,403)
        token=strict.get('/api/v1/auth/csrf/').data['csrfToken']
        with patch('management_api.customer_auth.send_transactional_mail'):
            result=strict.post('/api/v1/store/customer/send-code/',{'email':'a@example.com'},format='json',HTTP_X_CSRFTOKEN=token)
        self.assertEqual(result.status_code,200,result.data)

    def test_inactive_customer_cannot_login_or_use_allowance(self):
        self.verify(self.send());Customer.objects.update(active=False)
        self.assertFalse(self.client.get('/api/v1/store/ai-account/').data['authenticated'])
        EmailChallenge.objects.update(sent_at=timezone.now()-timedelta(minutes=2))
        self.assertEqual(self.verify(self.send()).status_code,403)

    def test_hourly_email_cap_and_new_code_invalidate_previous_code(self):
        with patch('management_api.customer_auth.secrets.randbelow', return_value=123456):
            old=self.send()
        EmailChallenge.objects.update(sent_at=timezone.now()-timedelta(minutes=2))
        with patch('management_api.customer_auth.secrets.randbelow', return_value=654321):
            new=self.send()
        self.assertEqual(self.verify(old).status_code,400)
        self.assertEqual(self.verify(new).status_code,200)
        EmailChallenge.objects.update(sent_count=5,sent_at=timezone.now()-timedelta(minutes=2))
        with patch('management_api.customer_auth.send_transactional_mail') as sender:
            response=self.client.post('/api/v1/store/customer/send-code/',{'email':'person@example.com'},format='json')
        self.assertEqual(response.status_code,429);sender.assert_not_called()

    def test_verified_customer_ai_mutations_still_require_csrf(self):
        self.verify(self.send())
        strict=APIClient(enforce_csrf_checks=True);strict.cookies=self.client.cookies
        self.assertEqual(strict.post('/api/v1/store/ai-renders/',{},format='json').status_code,403)
        token=strict.get('/api/v1/auth/csrf/').data['csrfToken']
        self.assertEqual(strict.post('/api/v1/store/ai-renders/',{},format='json',HTTP_X_CSRFTOKEN=token).status_code,400)


@override_settings(AI_CONFIG_ENCRYPTION_KEY=Fernet.generate_key().decode())
class MailConfigurationTests(TestCase):
    def setUp(self):
        cache.clear();self.client=APIClient()
        self.admin=User.objects.create_superuser(username='mail-admin',password='test-password-only')
        self.body={'enabled':True,'host':'smtp.example.com','port':587,'security':'starttls',
                   'username':'hello@example.com','password':'secret-canary','from_email':'hello@example.com',
                   'from_name':'POPOMO','revision':0}

    def test_only_admin_can_save_and_password_is_encrypted_and_retained(self):
        self.assertEqual(self.client.patch('/api/v1/admin/mail/',self.body,format='json').status_code,403)
        self.client.force_authenticate(self.admin)
        saved=self.client.patch('/api/v1/admin/mail/',self.body,format='json')
        self.assertEqual(saved.status_code,200,saved.data);self.assertNotIn('secret-canary',str(saved.data))
        c=SMTPConfig.objects.get();self.assertNotEqual(c.password_ciphertext,'secret-canary')
        self.assertEqual(cipher().decrypt(c.password_ciphertext.encode()).decode(),'secret-canary')
        retained=self.client.patch('/api/v1/admin/mail/',{**self.body,'password':'','revision':1},format='json')
        self.assertEqual(retained.status_code,200);self.assertTrue(retained.data['has_password'])
        self.assertEqual(self.client.patch('/api/v1/admin/mail/',self.body,format='json').status_code,409)

    def test_test_email_uses_saved_config_and_errors_are_redacted(self):
        self.client.force_authenticate(self.admin)
        self.client.patch('/api/v1/admin/mail/',self.body,format='json')
        with patch('management_api.mail_service.send_transactional_mail') as sender:
            result=self.client.post('/api/v1/admin/mail/test/',{'recipient':'owner@example.com','revision':1},format='json')
        self.assertEqual(result.status_code,200);self.assertEqual(sender.call_args.args[0],'owner@example.com')
        with patch('management_api.mail_service.send_transactional_mail',side_effect=Exception('secret-canary')):
            result=self.client.post('/api/v1/admin/mail/test/',{'recipient':'owner@example.com','revision':1},format='json')
        self.assertEqual(result.status_code,503);self.assertNotIn('secret-canary',str(result.data))

    def test_tls_validation_and_injection_rejected(self):
        self.client.force_authenticate(self.admin)
        for field,value in [('from_name','Store\r\nBcc: another@example.com'),('security','none'),('port',0),('host','https://smtp.example.com')]:
            self.assertEqual(self.client.patch('/api/v1/admin/mail/',{**self.body,field:value},format='json').status_code,400)

    def test_registration_settings_save_independently_with_permissions_and_revision(self):
        body = {'signup_credits': 7, 'revision': 0}
        self.assertEqual(self.client.patch('/api/v1/admin/registration/', body, format='json').status_code, 403)
        self.client.force_authenticate(self.admin)
        self.client.patch('/api/v1/admin/mail/', self.body, format='json')
        old_password = SMTPConfig.objects.get().password_ciphertext
        self.assertEqual(self.client.patch('/api/v1/admin/registration/', body, format='json').status_code, 409)
        response = self.client.patch('/api/v1/admin/registration/', {**body, 'revision': 1}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['signup_credits'], 7)
        self.assertEqual(SMTPConfig.objects.get().password_ciphertext, old_password)
        for count in [-1, 1001, 1.5, None]:
            self.assertEqual(self.client.patch('/api/v1/admin/registration/', {'revision': 2, 'signup_credits': count}, format='json').status_code, 400)
        # A subsequent SMTP edit must not replace the independently saved gift.
        self.assertEqual(self.client.patch('/api/v1/admin/mail/', {**self.body, 'revision': 2}, format='json').data['signup_credits'], 7)

    def test_bilingual_email_and_multipart_delivery(self):
        from django.core import mail
        from django.core.mail.backends.locmem import EmailBackend
        from .email_content import verification_email, test_email
        from .mail_service import send_transactional_mail
        config = SMTPConfig(host='smtp.example.com', from_email='hello@example.com')
        for language, expiry in [('en-US', 'Expires in 10 minutes'), ('zh-CN', '10 分钟内有效')]:
            subject, plain, html = verification_email('012345', language)
            self.assertIn('012345', plain)
            self.assertIn('012345', html)
            self.assertIn(expiry, html)
            with patch('management_api.mail_service.EmailBackend', return_value=EmailBackend()):
                send_transactional_mail('recipient@example.com', subject, plain, config, html_body=html)
            message = mail.outbox[-1]
            self.assertEqual(message.body, plain)
            self.assertEqual(message.alternatives[0].mimetype, 'text/html')
            self.assertEqual(message.alternatives[0].content, html)
        subject, plain, html = test_email()
        self.assertNotIn('012345', html)
        self.assertIn('发送成功', html)
