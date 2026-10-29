import base64
import hashlib
import json
import uuid
import urllib.error
from datetime import timedelta
from io import BytesIO, StringIO
from unittest.mock import patch, MagicMock

from cryptography.fernet import Fernet
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from .ai_generation import edit_image, GenerationError, run_render, restore_credit
from .ai_service import encrypt_api_key
from .models import AIAccount, AIRender, AIServiceConfig, AIStyle, Customer


def png():
    output=BytesIO(); Image.new('RGB',(24,32),'teal').save(output,format='PNG')
    return output.getvalue()


@override_settings(AI_CONFIG_ENCRYPTION_KEY=Fernet.generate_key().decode(), AI_DAILY_RENDER_LIMIT=20, AI_CONCURRENT_RENDER_LIMIT=2)
class LiveGenerationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_catalog',stdout=StringIO())
        call_command('seed_phone_templates',stdout=StringIO())
        AIServiceConfig.objects.create(pk=1,api_key_ciphertext=encrypt_api_key('test-not-a-real-api-key'),model_name='gpt-image-1-mini')
        AIStyle.objects.filter(code='anime').update(prompt='Private English style prompt')

    def setUp(self):
        cache.clear(); self.client=APIClient(); self.client.credentials(HTTP_X_ORDER_KEY='a'*64)
        self.customer=Customer.objects.create(email='ai@example.com',verified_at=timezone.now())
        self.login_customer(self.customer)
        key=hashlib.sha256(('customer:'+str(self.customer.pk)).encode()).hexdigest()
        AIAccount.objects.create(owner_hash=key,customer=self.customer,trial_granted=1)
        self.body={'request_key':str(uuid.uuid4()),'accepted':True,'photo':'data:image/png;base64,'+base64.b64encode(png()).decode(),'style_id':'anime','model':'iPhone 17'}

    def login_customer(self,customer):
        session=self.client.session
        if customer:session['store_customer_id']=str(customer.pk)
        else:session.pop('store_customer_id',None)
        session.save()

    def create(self, **changes):
        with patch('management_api.ai_generation.dispatch_render') as dispatch, self.captureOnCommitCallbacks(execute=True):
            response=self.client.post('/api/v1/store/ai-renders/',{**self.body,**changes},format='json')
        return response,dispatch

    def job(self):
        response,dispatch=self.create();self.assertEqual(response.status_code,202,response.data)
        self.assertEqual(dispatch.call_count,1)
        return AIRender.objects.get(pk=response.data['id'])

    def test_accepted_upload_creates_private_snapshot_and_reserves_once(self):
        job=self.job()
        self.assertEqual(job.input_image,png());self.assertIn('Private English style prompt',job.prompt)
        self.assertEqual(job.model_name,'gpt-image-1-mini');self.assertEqual(job.phone_template_id,'iphone-17-a-v1')
        self.assertEqual(AIAccount.objects.get().trial_used,1)
        response,dispatch=self.create();self.assertEqual(response.status_code,200);self.assertFalse(dispatch.called)
        self.assertEqual(AIRender.objects.count(),1);self.assertEqual(AIAccount.objects.get().trial_used,1)
        self.assertNotIn('Private English style prompt',str(response.data));self.assertNotIn('api_key',str(response.data))
        conflict,_=self.create(model='iPhone 16e');self.assertEqual(conflict.status_code,409)

    def test_rejects_missing_owner_consent_unknown_fields_and_invalid_images(self):
        for changes in ({'accepted':False},{'photo':'data:image/png;base64,AQID'},{'style_id':'missing'}, {'model':'Unknown'}, {'prompt':'override'}, {'api_key':'override'}):
            response,dispatch=self.create(**changes);self.assertEqual(response.status_code,400,changes);self.assertFalse(dispatch.called)
        self.login_customer(None);response,_=self.create();self.assertEqual(response.status_code,403)
        self.assertFalse(AIRender.objects.exists())

    def test_owner_controls_status_image_and_cancel(self):
        job=self.job();base=f'/api/v1/store/ai-renders/{job.id}/'
        self.login_customer(Customer.objects.create(email='other@example.com',verified_at=timezone.now()))
        self.assertEqual(self.client.get(base).status_code,404)
        self.assertEqual(self.client.post(base,{'action':'cancel'},format='json').status_code,404)
        with patch('management_api.ai_generation.edit_image',return_value=(png(),'test-request')):
            run_render(job.id)
        self.assertEqual(self.client.get(base+'image/').status_code,404)
        self.login_customer(self.customer)
        response=self.client.get(base+'image/');self.assertEqual(response.content,png());self.assertIn('no-store',response['Cache-Control'])
        self.assertNotIn('input_image',self.client.get(base).data)

    def test_worker_claims_once_and_does_not_finish_on_elapsed_time(self):
        job=self.job();url=f'/api/v1/store/ai-renders/{job.id}/'
        AIRender.objects.filter(pk=job.id).update(created_at=timezone.now()-timedelta(minutes=2))
        self.assertEqual(self.client.get(url).data['status'],'queued')
        with patch('management_api.ai_generation.edit_image',return_value=(png(),'test-request')) as provider:
            run_render(job.id);run_render(job.id)
        self.assertEqual(provider.call_count,1);job.refresh_from_db()
        self.assertEqual(job.status,'ready');self.assertEqual(bytes(job.input_image),b'');self.assertEqual(bytes(job.result_image),png())
        self.assertEqual(AIAccount.objects.get().trial_used,1)

    def test_failure_returns_generation_once_and_does_not_auto_retry(self):
        job=self.job()
        with patch('management_api.ai_generation.edit_image',side_effect=GenerationError('quota','No API credit.')) as provider:
            run_render(job.id);run_render(job.id)
        restore_credit(job,'failed');self.assertEqual(provider.call_count,1)
        job.refresh_from_db();self.assertEqual(job.status,'failed');self.assertTrue(job.credit_restored)
        self.assertEqual(AIAccount.objects.get().trial_used,0);self.assertEqual(bytes(job.input_image),b'')

    def test_cancel_and_stale_cleanup_return_allowance(self):
        job=self.job();url=f'/api/v1/store/ai-renders/{job.id}/'
        for _ in range(2):self.assertEqual(self.client.post(url,{'action':'cancel'},format='json').status_code,200)
        self.assertEqual(AIAccount.objects.get().trial_used,0)
        with patch('management_api.ai_generation.edit_image') as provider:run_render(job.id)
        self.assertFalse(provider.called)
        self.body['request_key']=str(uuid.uuid4());job=self.job()
        AIRender.objects.filter(pk=job.id).update(created_at=timezone.now()-timedelta(minutes=11))
        self.assertEqual(self.client.get(f'/api/v1/store/ai-renders/{job.id}/').data['status'],'failed')
        self.assertEqual(AIAccount.objects.get().trial_used,0)

    def test_server_quota_prevents_parallel_and_extra_free_jobs(self):
        job=self.job();self.body['request_key']=str(uuid.uuid4())
        self.assertEqual(self.create()[0].status_code,409)
        with patch('management_api.ai_generation.edit_image',return_value=(png(),'')):run_render(job.id)
        self.assertEqual(self.create()[0].status_code,409)
        self.assertEqual(AIRender.objects.count(),1)

    @override_settings(AI_DAILY_RENDER_LIMIT=0)
    def test_global_daily_limit_reserves_nothing(self):
        self.assertEqual(self.create()[0].status_code,429);self.assertFalse(AIRender.objects.exists())

    @override_settings(DEBUG=False)
    def test_production_cannot_mint_demo_subscription(self):
        result=self.client.post('/api/v1/store/ai-account/',{'action':'subscribe','accepted':True},format='json')
        self.assertEqual(result.status_code,403)

    def test_edit_request_uses_uploaded_bytes_and_saved_model(self):
        job=self.job();reply=MagicMock();reply.read.return_value=json.dumps({'data':[{'b64_json':base64.b64encode(png()).decode()}]}).encode();reply.headers={'x-request-id':'request-123'}
        opener=MagicMock();opener.open.return_value.__enter__.return_value=reply
        with patch('management_api.ai_generation.urllib.request.build_opener',return_value=opener):
            output,request_id=edit_image('test-not-a-real-api-key',job)
        request=opener.open.call_args.args[0]
        self.assertEqual(request.full_url,'https://api.openai.com/v1/images/edits')
        for part in (png(),b'name="image[]"',b'gpt-image-1-mini',b'Private English style prompt',b'1024x1536'):
            self.assertIn(part,request.data)
        self.assertNotIn(b'input_fidelity',request.data)
        self.assertEqual(output,png());self.assertEqual(request_id,'request-123')

    def test_provider_errors_never_echo_credentials_or_raw_body(self):
        job=self.job();error=urllib.error.HTTPError('https://api.openai.com/v1/images/edits',429,'error',{},BytesIO(b'{"error":{"code":"insufficient_quota","message":"private-canary-token"}}'))
        opener=MagicMock();opener.open.side_effect=error
        with patch('management_api.ai_generation.urllib.request.build_opener',return_value=opener):
            with self.assertRaises(GenerationError) as caught:edit_image('private-canary-key',job)
        self.assertEqual(caught.exception.code,'quota');self.assertNotIn('private-canary',str(caught.exception))

    def test_current_billing_and_rate_limit_codes_remain_distinguishable(self):
        job=self.job()
        for code in ('credit_balance_exhausted','project_spend_limit_exceeded','organization_spend_limit_exceeded','organization_usage_limit_exceeded','rate_limit_exceeded','slow_down'):
            error=urllib.error.HTTPError('https://api.openai.com/v1/images/edits',429,'error',{},BytesIO(json.dumps({'error':{'code':code,'message':'private-canary'}}).encode()))
            opener=MagicMock();opener.open.side_effect=error
            with patch('management_api.ai_generation.urllib.request.build_opener',return_value=opener):
                with self.assertRaises(GenerationError) as caught:edit_image('private-canary-key',job)
            self.assertEqual(caught.exception.code,code);self.assertNotIn('private-canary',str(caught.exception))
