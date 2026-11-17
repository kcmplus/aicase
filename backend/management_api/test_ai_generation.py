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
from .ai_service import encrypt_api_key, switch_provider, NoRedirect
from .models import AIAccount, AIRender, AIServiceConfig, AIStyle, Customer, CreditEntry, PhoneModel


def png():
    output=BytesIO(); Image.new('RGB',(24,32),'teal').save(output,format='PNG')
    return output.getvalue()


@override_settings(AI_CONFIG_ENCRYPTION_KEY=Fernet.generate_key().decode(), AI_DAILY_RENDER_LIMIT=20, AI_CONCURRENT_RENDER_LIMIT=2)
class LiveGenerationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_catalog',stdout=StringIO())
        call_command('seed_phone_templates',stdout=StringIO())
        cls.seeded_anime_prompt = AIStyle.objects.get(code='anime').prompt
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
        self.assertTrue(job.prompt.startswith('PHONE-CASE CAMERA CUTOUT SAFETY'))
        self.assertIn('Target phone model: iPhone 17.', job.prompt)
        self.assertEqual(job.model_name,'gpt-image-1-mini');self.assertEqual(job.phone_template_id,'iphone-17-a-v1')
        self.assertEqual(AIAccount.objects.get().trial_used,1)
        response,dispatch=self.create();self.assertEqual(response.status_code,200);self.assertFalse(dispatch.called)
        self.assertEqual(AIRender.objects.count(),1);self.assertEqual(AIAccount.objects.get().trial_used,1)
        entry=CreditEntry.objects.get(kind='generation');self.assertEqual(entry.amount,-1);self.assertEqual(entry.balance_after,0)
        self.assertNotIn('Private English style prompt',str(response.data));self.assertNotIn('api_key',str(response.data))
        conflict,_=self.create(model='iPhone 16e');self.assertEqual(conflict.status_code,409)

    def test_composition_is_frozen_with_idempotency_and_invalid_template_costs_nothing(self):
        invalid, dispatch = self.create(phone_template_id='iphone-16e-v1')
        self.assertEqual(invalid.status_code, 400)
        self.assertFalse(dispatch.called)
        self.assertEqual(AIAccount.objects.get().trial_used, 0)
        self.body.update(phone_template_id='iphone-17-a-v1', case_material='standard')
        response, dispatch = self.create()
        self.assertEqual(response.status_code, 202, response.data)
        job = AIRender.objects.get(pk=response.data['id'])
        frozen = job.composition_snapshot
        self.assertEqual(response.data['composition']['fit'], 'blur')
        self.assertIn('TEMPLATE-BASED COMPOSITION', job.prompt)
        self.assertIn('COMPLETE head', job.prompt)
        self.assertNotIn('image_safe', response.data['composition'])
        PhoneModel.objects.filter(name='iPhone 17').update(composition_revision=10)
        again, dispatch = self.create()
        self.assertEqual(again.status_code, 200)
        self.assertFalse(dispatch.called)
        job.refresh_from_db()
        self.assertEqual(job.composition_snapshot, frozen)
        self.assertEqual(self.create(case_material='magnetic')[0].status_code, 409)
        self.assertEqual(self.create(phone_template_id='')[0].status_code, 409)
        self.assertEqual(AIRender.objects.count(), 1)
        self.assertEqual(AIAccount.objects.get().trial_used, 1)

    def test_published_model_without_bundled_template_can_generate_and_retry_once(self):
        model = PhoneModel.objects.create(brand=PhoneModel.objects.get(name='iPhone 17').brand,
            code='iphone-13-pro', name='iPhone 13 Pro', active=True, adaptation_prompt='Keep the portrait centered.')
        # This is an actual published catalog choice with no stock/template.
        catalog = self.client.get('/api/v1/store/phone-models/').data
        choice = next(item for item in catalog['models'] if item['name'] == model.name)
        self.assertNotIn('templateId', choice)
        response, dispatch = self.create(model=model.name)
        self.assertEqual(response.status_code, 202, response.data)
        self.assertEqual(dispatch.call_count, 1)
        job = AIRender.objects.get(pk=response.data['id'])
        self.assertEqual(job.phone_model, model.name)
        self.assertEqual(job.phone_template_id, '')
        self.assertEqual(response.data['phoneTemplateId'], '')
        self.assertIn('Exact case template geometry is not available', job.prompt)
        self.assertIn('Keep the portrait centered.', job.prompt)
        self.assertNotIn('The final case canvas ratio is', job.prompt)
        self.assertTrue(job.prompt.startswith('PHONE-CASE CAMERA CUTOUT SAFETY'))
        self.assertEqual(AIAccount.objects.get().trial_used, 1)
        again, dispatch = self.create(model=model.name)
        self.assertEqual(again.status_code, 200)
        self.assertFalse(dispatch.called)
        self.assertEqual(AIRender.objects.count(), 1)
        self.assertEqual(CreditEntry.objects.filter(kind='generation').count(), 1)
        # Generating a design cannot grant print eligibility for an unknown template.
        from .orders import Snapshot
        snapshot = Snapshot(data={'version': 2, 'code': 'POP-C-0123456789ABCDEF',
            'source': 'collection', 'designId': 'bloom', 'model': model.name,
            'caseMaterial': 'standard', 'photo': '', 'effect': 'original',
            'intensity': 65, 'zoom': 100, 'x': 50, 'y': 50})
        self.assertFalse(snapshot.is_valid())

    def test_unpublished_models_or_brands_do_not_reserve_generation_credit(self):
        model = PhoneModel.objects.create(brand=PhoneModel.objects.get(name='iPhone 17').brand,
            code='unpublished-phone', name='Unpublished Phone', active=False)
        response, dispatch = self.create(model=model.name)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(dispatch.called)
        model.active = True; model.save()
        model.brand.active = False; model.brand.save()
        response, dispatch = self.create(model=model.name)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(dispatch.called)
        self.assertEqual(AIAccount.objects.get().trial_used, 0)
        self.assertFalse(AIRender.objects.exists())
        self.assertFalse(CreditEntry.objects.filter(kind='generation').exists())

    def test_default_catalog_styles_accept_generation_without_manual_prompt_edits(self):
        AIStyle.objects.filter(code='anime').update(prompt=self.seeded_anime_prompt)
        for code in ('anime', 'realism', '3d'):
            self.body.update(style_id=code, request_key=str(uuid.uuid4()))
            job = self.job()
            self.assertIn(AIStyle.objects.get(code=code).prompt, job.prompt)
            self.assertTrue(job.prompt.startswith('PHONE-CASE CAMERA CUTOUT SAFETY'))
            self.assertLess(job.prompt.index('Keep faces, eyes'), job.prompt.index('\n\nSTYLE\n'))
            restore_credit(job, 'cancelled')
        self.assertEqual(AIAccount.objects.get().trial_used, 0)

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
        self.assertEqual(job.status,'ready');self.assertEqual(bytes(job.input_image),png());self.assertEqual(bytes(job.result_image),png())
        self.assertEqual(AIAccount.objects.get().trial_used,1)

    def test_failure_returns_generation_once_and_does_not_auto_retry(self):
        job=self.job()
        with patch('management_api.ai_generation.edit_image',side_effect=GenerationError('quota','No API credit.')) as provider:
            run_render(job.id);run_render(job.id)
        restore_credit(job,'failed');self.assertEqual(provider.call_count,1)
        self.assertEqual(CreditEntry.objects.filter(kind='failure_refund').count(),1)
        self.assertEqual(CreditEntry.objects.get(kind='failure_refund').amount,1)
        job.refresh_from_db();self.assertEqual(job.status,'failed');self.assertTrue(job.credit_restored)
        self.assertEqual(AIAccount.objects.get().trial_used,0);self.assertEqual(bytes(job.input_image),png())

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

    def test_bonus_credits_can_be_used_and_refunded_without_resetting_usage(self):
        AIAccount.objects.update(trial_used=1, bonus_granted=2)
        response=self.create()[0];self.assertEqual(response.status_code,202,response.data)
        self.assertEqual(AIAccount.objects.get().trial_used,2)
        self.assertEqual(self.client.get('/api/v1/store/ai-account/').data['trialRemaining'],1)
        self.assertEqual(self.client.post('/api/v1/store/ai-renders/'+response.data['id']+'/',{'action':'cancel'},format='json').status_code,200)
        self.assertEqual(AIAccount.objects.get().trial_used,1)
        self.assertEqual(self.client.get('/api/v1/store/ai-account/').data['trialRemaining'],2)

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
        for part in (png(),b'name="image[]"',b'gpt-image-1-mini',b'Private English style prompt',
                     b'PHONE-CASE CAMERA CUTOUT SAFETY',b'1024x1536'):
            self.assertIn(part,request.data)
        self.assertNotIn(b'input_fidelity',request.data)
        self.assertEqual(output,png());self.assertEqual(request_id,'request-123')

    def use_relay(self):
        config = AIServiceConfig.objects.get()
        switch_provider(config, 'ai778')
        config.api_key_ciphertext = encrypt_api_key('relay-only-key')
        config.save()
        self.body['provider'] = 'ai778'

    def test_relay_upload_uses_documented_fields_endpoint_and_task_id(self):
        self.use_relay()
        job = self.job()
        self.assertEqual(job.provider, 'ai778')
        self.assertEqual(job.model_name, 'tt-image-2')
        with patch('management_api.ai_generation.urllib.request.build_opener') as build:
            reply = build.return_value.open.return_value.__enter__.return_value
            reply.read.return_value = json.dumps({'data': [{'b64_json': base64.b64encode(png()).decode()}]}).encode()
            reply.headers = {'X-Task-Id': '123456'}
            output, request_id = edit_image('relay-only-key', job)
        request = build.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url, 'https://api.lk888.ai/v1/images/edits')
        self.assertEqual(request.get_header('Authorization'), 'Bearer relay-only-key')
        self.assertIsInstance(build.call_args.args[0], NoRedirect)
        for field in (png(), b'name="image"', b'tt-image-2', b'1024x1536', b'b64_json'):
            self.assertIn(field, request.data)
        for field in (b'name="background"', b'name="output_format"', b'name="safety_identifier"', b'name="image[]"'):
            self.assertNotIn(field, request.data)
        self.assertEqual(output, png())
        self.assertEqual(request_id, '123456')

    def test_queued_jobs_keep_original_provider_after_switch(self):
        job = self.job()
        self.use_relay()
        with patch('management_api.ai_generation.edit_image', return_value=(png(), '')) as edit:
            run_render(job.id)
        key, queued = edit.call_args.args
        self.assertEqual(key, 'test-not-a-real-api-key')
        self.assertEqual(queued.provider, 'openai')

    def test_relay_job_uses_relay_key_after_switching_back(self):
        self.use_relay()
        job = self.job()
        config = AIServiceConfig.objects.get()
        switch_provider(config, 'openai')
        config.save()
        with patch('management_api.ai_generation.edit_image', return_value=(png(), '')) as edit:
            run_render(job.id)
        key, queued = edit.call_args.args
        self.assertEqual(key, 'relay-only-key')
        self.assertEqual(queued.provider, 'ai778')

    def test_provider_change_requires_fresh_consent_and_does_not_charge(self):
        self.use_relay()
        response, dispatch = self.create(provider='openai')
        self.assertEqual(response.status_code, 409)
        dispatch.assert_not_called()
        self.assertFalse(AIRender.objects.exists())
        self.assertEqual(AIAccount.objects.get().trial_used, 0)
        self.assertFalse(CreditEntry.objects.exists())

    def test_relay_can_spend_bonus_credits_and_records_one_failure_refund(self):
        self.use_relay()
        AIAccount.objects.update(trial_granted=0, bonus_granted=1)
        job = self.job()
        charge = CreditEntry.objects.get(kind='generation', render_id=job.pk)
        self.assertEqual((charge.pool, charge.amount, charge.balance_after), ('gift', -1, 0))
        with patch('management_api.ai_generation.edit_image', side_effect=GenerationError('network', 'Try later.')):
            run_render(job.pk)
            run_render(job.pk)
        refund = CreditEntry.objects.get(kind='failure_refund', render_id=job.pk)
        self.assertEqual((refund.pool, refund.amount, refund.balance_after), ('gift', 1, 1))
        account = self.client.get('/api/v1/store/ai-account/').data
        self.assertEqual((account['bonusGranted'], account['trialRemaining']), (1, 1))

    def test_relay_rejects_url_only_results_without_fetching_or_leaking(self):
        self.use_relay()
        job = self.job()
        with patch('management_api.ai_generation.urllib.request.build_opener') as build:
            reply = build.return_value.open.return_value.__enter__.return_value
            reply.read.return_value = json.dumps({'data': [{'url': 'http://127.0.0.1/private-canary'}]}).encode()
            reply.headers = {}
            with self.assertRaises(GenerationError) as caught:
                edit_image('relay-only-key', job)
            self.assertEqual(caught.exception.code, 'invalid_response')
            self.assertNotIn('private-canary', str(caught.exception))
            self.assertEqual(build.return_value.open.call_count, 1)

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
