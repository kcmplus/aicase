import base64
import json
import urllib.error
import uuid
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from .ai_costs import estimate_cost, price_snapshot, safe_usage, sync_relay_cost
from .ai_generation import run_render
from .ai_service import encrypt_api_key, switch_provider
from .models import AIAccount, AIRender, AIServiceConfig, AuditLog

USAGE = {'input_tokens': 300, 'output_tokens': 300, 'total_tokens': 600,
         'input_tokens_details': {'text_tokens': 100, 'image_tokens': 200}}
KEY = 'test-only-private-api-key'


class CostCalculationTests(SimpleTestCase):
    def test_multimodal_cost_uses_tokens_and_exact_decimal_rates(self):
        cost, reason, parts = estimate_cost(USAGE, price_snapshot('openai', 'gpt-image-2.5-flare'))
        self.assertEqual(cost, Decimal('0.01110000'))
        self.assertEqual(reason, 'usage_estimate')
        self.assertEqual(sum(Decimal(value) for value in parts.values()), cost)
        self.assertEqual(estimate_cost(USAGE, price_snapshot('openai', 'gpt-image-1-mini'))[0], Decimal('0.00310000'))
        self.assertEqual(price_snapshot('ai778', 'tt-image-2'), {})

    def test_missing_partial_and_inconsistent_usage_are_not_zero_cost(self):
        price = price_snapshot('openai', 'gpt-image-2')
        for usage in ({}, {'output_tokens': 200}, {**USAGE, 'input_tokens': 301}, {**USAGE, 'total_tokens': 601},
                      {**USAGE, 'output_tokens_details': {'text_tokens': 2}},
                      {**USAGE, 'output_tokens_details': {'text_tokens': 2, 'image_tokens': 299}}):
            self.assertIsNone(estimate_cost(usage, price)[0])
        self.assertIsNone(estimate_cost(USAGE, {})[0])
        zero = {'input_tokens': 0, 'output_tokens': 0, 'input_tokens_details': {'text_tokens': 0, 'image_tokens': 0}}
        self.assertEqual(estimate_cost(zero, price)[0], Decimal('0'))

    def test_text_outputs_are_priced_separately_and_direct_images_do_not_use_cache_discount(self):
        usage = {**USAGE, 'output_tokens_details': {'image_tokens': 290, 'text_tokens': 10}}
        self.assertEqual(estimate_cost(usage, price_snapshot('openai', 'gpt-image-1.5'))[0], Decimal('0.01148000'))
        self.assertIsNone(estimate_cost(usage, price_snapshot('openai', 'gpt-image-2.5-flare'))[0])
        usage = {**USAGE, 'input_tokens_details': {**USAGE['input_tokens_details'], 'cached_tokens': 200}}
        self.assertEqual(estimate_cost(usage, price_snapshot('openai', 'gpt-image-2'))[0], Decimal('0.01110000'))

    def test_usage_allowlist_drops_secrets_and_invalid_counters(self):
        result = safe_usage({**USAGE, 'secret': KEY, 'total_tokens': True, 'output_tokens': -1,
                             'input_tokens_details': {'text_tokens': '100', 'image_tokens': 200, 'prompt': KEY}})
        self.assertEqual(result, {'input_tokens': 300, 'input_tokens_details': {'image_tokens': 200}})
        for value in (None, [], KEY):
            self.assertEqual(safe_usage(value), {})


@override_settings(AI_CONFIG_ENCRYPTION_KEY=Fernet.generate_key().decode())
class CallReportingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.root = get_user_model().objects.create_superuser('report-root', password='report-test-password')
        cls.staff = get_user_model().objects.create_user('report-staff', is_staff=True)
        AIServiceConfig.objects.create(pk=1, api_key_ciphertext=encrypt_api_key(KEY))
        AIAccount.objects.create(owner_hash='a'*64, trial_granted=1, trial_used=1)

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.client.force_login(self.root)

    def job(self, **values):
        defaults = dict(request_key=uuid.uuid4(), owner_hash='a'*64, model_name='gpt-image-2.5-flare',
            input_image=self.image(), input_mime='image/png', prompt='private-prompt-canary',
            style_name='Portrait', phone_model='iPhone 17', allocation={'type': 'trial'})
        return AIRender.objects.create(**{**defaults, **values})

    def image(self):
        buffer = BytesIO()
        Image.new('RGB', (24, 32), 'teal').save(buffer, format='PNG')
        return buffer.getvalue()

    def reply(self, data, headers=None):
        reply = MagicMock()
        reply.__enter__.return_value = reply
        reply.read.return_value = json.dumps(data).encode()
        reply.status = 200
        reply.headers = headers or {'x-request-id': 'req-example'}
        return reply

    @patch('management_api.ai_generation.urllib.request.build_opener')
    def test_success_records_usage_cost_and_latency_once_without_raw_payloads(self, build):
        job = self.job()
        build.return_value.open.return_value = self.reply({'usage': {**USAGE, 'secret': KEY},
            'data': [{'b64_json': base64.b64encode(self.image()).decode(), 'revised_prompt': KEY}]})
        run_render(job.pk)
        run_render(job.pk)
        self.assertEqual(build.return_value.open.call_count, 1)
        job.refresh_from_db()
        self.assertEqual(job.status, 'ready')
        self.assertEqual(job.http_status, 200)
        self.assertEqual(job.provider_request_id, 'req-example')
        self.assertIsNotNone(job.api_duration_ms)
        self.assertGreaterEqual(job.api_finished_at, job.api_started_at)
        self.assertEqual(job.cost_amount, Decimal('0.0111'))
        self.assertEqual((job.cost_source, job.cost_currency), ('estimated', 'USD'))
        self.assertEqual(job.usage, USAGE)
        self.assertNotIn(KEY, str(job.cost_details)+str(job.request_params))

    @patch('management_api.ai_generation.urllib.request.build_opener')
    def test_http_failure_keeps_request_id_and_status_but_unknown_cost(self, build):
        job = self.job()
        build.return_value.open.side_effect = urllib.error.HTTPError('https://api.openai.com/v1/images/edits', 429,
            KEY, {'x-request-id': 'req-failed'}, BytesIO(json.dumps({'error': {'code': 'credit_balance_exhausted', 'message': KEY}}).encode()))
        run_render(job.pk)
        job.refresh_from_db()
        self.assertEqual((job.status, job.http_status, job.provider_request_id), ('failed', 429, 'req-failed'))
        self.assertEqual(job.error_code, 'credit_balance_exhausted')
        self.assertTrue(job.credit_restored)
        self.assertIsNone(job.cost_amount)
        self.assertNotIn(KEY, job.error_message)

    @patch('management_api.ai_generation.urllib.request.build_opener')
    def test_unreadable_image_can_still_have_upstream_cost(self, build):
        job = self.job()
        build.return_value.open.return_value = self.reply({'usage': USAGE, 'data': [{'b64_json': 'invalid'}]})
        run_render(job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, 'failed')
        self.assertTrue(job.credit_restored)
        self.assertEqual(job.cost_amount, Decimal('0.0111'))

    @patch('management_api.ai_generation.urllib.request.build_opener')
    def test_timeout_is_logged_and_not_retried_or_assumed_free(self, build):
        job = self.job()
        build.return_value.open.side_effect = TimeoutError(KEY)
        run_render(job.pk)
        job.refresh_from_db()
        self.assertEqual(job.error_code, 'network')
        self.assertIsNone(job.http_status)
        self.assertIsNone(job.cost_amount)
        self.assertIsNotNone(job.api_duration_ms)
        self.assertEqual(build.return_value.open.call_count, 1)

    @patch('management_api.ai_costs.urllib.request.build_opener')
    def test_relay_reads_only_matching_final_net_cost_in_compute_credits(self, build):
        job = self.job(provider='ai778', model_name='tt-image-2', provider_request_id='12345', status='ready')
        build.return_value.open.return_value = self.reply({'task_id': 12345, 'is_final': True, 'state': 'success',
            'cost': '0.0455', 'result_url': 'http://private.invalid/secret', 'input_files': [KEY]})
        sync_relay_cost(job, KEY)
        job.refresh_from_db()
        self.assertEqual((job.cost_amount, job.cost_source, job.cost_currency), (Decimal('0.0455'), 'reported', 'AI778'))
        request = build.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url, 'https://api.lk888.ai/v1/skills/task-status?task_id=12345')
        self.assertEqual(request.get_method(), 'GET')
        self.assertNotIn(KEY, str(job.cost_details))
        sync_relay_cost(job, KEY)
        self.assertEqual(build.return_value.open.call_count, 1)

    @patch('management_api.ai_costs.urllib.request.build_opener')
    def test_relay_precharge_mismatch_and_invalid_cost_stay_unknown(self, build):
        base = {'task_id': 12345, 'is_final': True, 'state': 'success', 'cost': '1.5'}
        job = self.job(provider='ai778', provider_request_id='12345', status='ready')
        for changes in ({'is_final': False}, {'task_id': 999}, {'cost': -1}, {'cost': True}, {'cost': 'NaN'}, {'cost': 'Infinity'}, {'cost': None}):
            build.return_value.open.return_value = self.reply({**base, **changes})
            sync_relay_cost(job, KEY)
            job.refresh_from_db()
            self.assertIsNone(job.cost_amount, changes)
        build.return_value.open.return_value = self.reply({**base, 'state': 'failed', 'cost': 0, 'refunded_amount': 1.5})
        sync_relay_cost(job, KEY)
        job.refresh_from_db()
        self.assertEqual(job.cost_amount, Decimal('0'))  # Already net of the refund; do not subtract again.
        self.assertEqual(job.cost_source, 'reported')

    @patch('management_api.ai_costs.urllib.request.build_opener')
    def test_failed_relay_cost_lookup_preserves_a_delivered_image(self, build):
        job = self.job(provider='ai778', model_name='tt-image-2')
        config = AIServiceConfig.objects.get()
        switch_provider(config, 'ai778')
        config.api_key_ciphertext = encrypt_api_key(KEY)
        config.save()
        response = self.reply({'data': [{'b64_json': base64.b64encode(self.image()).decode()}]}, {'X-Task-Id': '12345'})
        def open_request(request, **kwargs):
            if '/images/edits' in request.full_url:
                return response
            self.assertEqual(AIRender.objects.get(pk=job.pk).status, 'ready')
            raise TimeoutError(KEY)
        build.return_value.open.side_effect = open_request
        run_render(job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, 'ready')
        self.assertFalse(job.credit_restored)
        self.assertEqual(job.cost_details['reason'], 'relay_lookup_failed')

    def test_logs_and_reporting_require_superuser_and_exclude_private_fields(self):
        job = self.job(status='ready', usage=USAGE)
        paths = ['/api/v1/admin/ai-usage/', '/api/v1/admin/ai-renders/']
        for user in (None, self.staff):
            self.client.logout()
            if user:
                self.client.force_login(user)
            for path in paths:
                self.assertEqual(self.client.get(path).status_code, 403)
            self.assertEqual(self.client.post(f'/api/v1/admin/ai-renders/{job.pk}/cost/').status_code, 403)
        self.client.force_login(self.root)
        for path in paths:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, response.data)
            self.assertIn('no-store', response['Cache-Control'])
            for secret in ('private-prompt-canary', 'owner_hash', 'input_image', 'result_image', 'api_key_ciphertext', KEY):
                self.assertNotIn(secret, response.content.decode())

    def test_summary_separates_units_unknown_costs_and_counting_after_filters(self):
        self.job(status='ready', cost_amount=Decimal('.01'), cost_source='estimated', cost_currency='USD', api_duration_ms=1000)
        self.job(status='failed', cost_amount=Decimal('.02'), cost_source='estimated', cost_currency='USD', api_duration_ms=3000)
        self.job(status='ready', provider='ai778', model_name='tt-image-2', cost_amount=Decimal('.0455'), cost_source='reported', cost_currency='AI778')
        legacy = self.job(status='ready')
        self.job(status='queued')
        data = self.client.get('/api/v1/admin/ai-usage/').data
        summary = data['summary']
        self.assertEqual((summary['total'], summary['ready'], summary['failed'], summary['pending'], summary['unpriced']), (5, 3, 1, 1, 1))
        self.assertEqual(summary['success_rate'], 75)
        self.assertEqual(summary['avg_duration_ms'], 2000)
        costs = {row['cost_currency']: row['total'] for row in summary['costs']}
        self.assertEqual(costs, {'USD': '0.03000000', 'AI778': '0.04550000'})
        self.assertEqual(sum(day['total'] for day in data['daily']), 5)
        self.assertEqual(sum(row['total'] for row in data['models']), 5)
        filtered = self.client.get('/api/v1/admin/ai-usage/', {'provider': 'openai', 'status': 'ready'}).data['summary']
        self.assertEqual((filtered['total'], filtered['unpriced']), (2, 1))
        rows = self.client.get('/api/v1/admin/ai-renders/', {'page_size': 2, 'page': 2}).data
        self.assertEqual((rows['count'], len(rows['results']), rows['page']), (5, 2, 2))
        row = self.client.get('/api/v1/admin/ai-renders/', {'search': str(legacy.pk)}).data
        self.assertEqual(row['count'], 1)
        self.assertIsNone(row['results'][0]['cost_amount'])

    def test_local_calendar_boundaries_and_invalid_ranges(self):
        before = self.job(status='ready')
        inside = self.job(status='ready')
        after = self.job(status='ready')
        for job, stamp in ((before, '2026-01-01T23:59:59'), (inside, '2026-01-02T00:00:00'), (after, '2026-01-03T00:00:00')):
            AIRender.objects.filter(pk=job.pk).update(created_at=datetime.fromisoformat(stamp).replace(tzinfo=ZoneInfo('Asia/Shanghai')))
        query = {'start': '2026-01-02', 'end': '2026-01-02'}
        self.assertEqual(self.client.get('/api/v1/admin/ai-renders/', query).data['count'], 1)
        for query in ({'start': '2026-01-04', 'end': '2026-01-02'}, {'start': '2020-01-01'}, {'provider': 'bad'}, {'page_size': 999}, {'page': -1}, {'start': 'bad'}, {'start': '9999-12-31', 'end': '9999-12-31'}):
            self.assertEqual(self.client.get('/api/v1/admin/ai-renders/', query).status_code, 400, query)

    def test_empty_period_does_not_claim_free_cost_or_success(self):
        summary = self.client.get('/api/v1/admin/ai-usage/').data['summary']
        self.assertEqual(summary['costs'], [])
        self.assertIsNone(summary['success_rate'])
        self.assertIsNone(summary['avg_duration_ms'])

    @patch('management_api.ai_costs.urllib.request.build_opener')
    def test_cost_backfill_uses_saved_relay_key_even_when_openai_is_selected(self, build):
        config = AIServiceConfig.objects.get()
        switch_provider(config, 'ai778')
        config.api_key_ciphertext = encrypt_api_key('relay-private-key')
        switch_provider(config, 'openai')
        config.save()
        job = self.job(provider='ai778', status='ready', provider_request_id='12345')
        build.return_value.open.return_value = self.reply({'task_id': 12345, 'is_final': True, 'state': 'success', 'cost': '.0455'})
        result = self.client.post(f'/api/v1/admin/ai-renders/{job.pk}/cost/')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data['cost_amount'], '0.04550000')
        self.assertEqual(build.return_value.open.call_args.args[0].get_header('Authorization'), 'Bearer relay-private-key')
        self.assertNotIn('relay-private-key', str(result.data)+str(list(AuditLog.objects.values())))
        self.assertEqual(AIServiceConfig.objects.get().provider, 'openai')

    def test_cost_refresh_requires_csrf(self):
        job = self.job(provider='ai778', status='ready', provider_request_id='12345')
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.root)
        self.assertEqual(client.post(f'/api/v1/admin/ai-renders/{job.pk}/cost/').status_code, 403)
