import hashlib
import importlib
import uuid
from datetime import timedelta
from decimal import Decimal
from io import BytesIO, StringIO
from unittest.mock import patch

from cryptography.fernet import Fernet
from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from .ai_generation import run_render
from .ai_images import cleanup_expired_images
from .ai_service import encrypt_api_key
from .models import AIRender, AIServiceConfig, Customer


@override_settings(AI_CONFIG_ENCRYPTION_KEY=Fernet.generate_key().decode())
class AIImageRetentionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.root = get_user_model().objects.create_superuser('image-root', password='image-test-password')
        cls.staff = get_user_model().objects.create_user('image-staff', is_staff=True)
        cls.customer = Customer.objects.create(email='images@example.com', verified_at=timezone.now())
        AIServiceConfig.objects.create(pk=1, api_key_ciphertext=encrypt_api_key('test-private-key'),
                                       last_check_status='ok')

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.client.force_login(self.root)
        self.now = timezone.now()
        output = BytesIO()
        Image.new('RGB', (24, 32), 'teal').save(output, format='PNG')
        self.png = output.getvalue()

    def job(self, **values):
        return AIRender.objects.create(**{**dict(request_key=uuid.uuid4(), status='ready',
            owner_hash=hashlib.sha256(('customer:'+str(self.customer.pk)).encode()).hexdigest(),
            model_name='gpt-image-2', input_image=b'', result_image=self.png,
            prompt='private-prompt', image_expires_at=self.now+timedelta(days=30),
            cost_amount=Decimal('.01'), cost_currency='USD', cost_source='estimated'), **values})

    def image_url(self, job):
        return f'/api/v1/admin/ai-renders/{job.pk}/image/'

    def test_preview_and_download_deliver_png_without_public_caching(self):
        job = self.job()
        for suffix, disposition in (('', 'inline'), ('?download=1', 'attachment')):
            response = self.client.get(self.image_url(job)+suffix)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, self.png)
            self.assertEqual(response['Content-Type'], 'image/png')
            self.assertEqual(response['Content-Disposition'], f'{disposition}; filename="ai-{job.pk}.png"')
            self.assertIn('private', response['Cache-Control'])
            self.assertIn('no-store', response['Cache-Control'])
            self.assertEqual(response['X-Content-Type-Options'], 'nosniff')

    def test_admin_images_reject_anonymous_staff_and_inactive_superuser(self):
        job = self.job()
        inactive = get_user_model().objects.create_user('disabled-image-root', is_superuser=True, is_staff=True, is_active=False)
        for user in (None, self.staff, inactive):
            self.client.logout()
            if user:
                self.client.force_login(user)
            for suffix in ('', '?download=1'):
                response = self.client.get(self.image_url(job)+suffix)
                self.assertEqual(response.status_code, 403)
                self.assertNotIn(self.png, response.content)

    def test_expiry_denies_access_before_cleanup_and_missing_or_unfinished_images_are_not_served(self):
        expired = self.job(image_expires_at=self.now)
        for suffix in ('', '?download=1'):
            response = self.client.get(self.image_url(expired)+suffix)
            self.assertEqual(response.status_code, 410)
            self.assertEqual(response.data['code'], 'image_expired')
            self.assertIn('no-store', response['Cache-Control'])
        expired.refresh_from_db()
        self.assertEqual(bytes(expired.result_image), self.png)
        for changes in ({'status': 'generating'}, {'status': 'failed'}, {'result_image': None}, {'result_image': b''}):
            self.assertEqual(self.client.get(self.image_url(self.job(**changes))).status_code, 404)

    def test_cleanup_is_bounded_idempotent_and_preserves_usage_and_costs(self):
        expired = [self.job(image_expires_at=self.now-timedelta(days=1), usage={'total_tokens': 99}) for _ in range(3)]
        protected = [self.job(), self.job(status='generating', image_expires_at=self.now), self.job(status='failed', image_expires_at=self.now)]
        self.assertEqual(cleanup_expired_images(now=self.now, batch_size=2, max_batches=1), 2)
        self.assertEqual(cleanup_expired_images(now=self.now), 1)
        self.assertEqual(cleanup_expired_images(now=self.now), 0)
        for job in expired:
            job.refresh_from_db()
            self.assertIsNone(job.result_image)
            self.assertEqual(job.image_deleted_at, self.now)
            self.assertEqual((job.status, job.cost_amount, job.cost_currency, job.usage),
                             ('ready', Decimal('.01'), 'USD', {'total_tokens': 99}))
        for job in protected:
            job.refresh_from_db()
            self.assertEqual(bytes(job.result_image), self.png)
        self.assertEqual(AIRender.objects.count(), 6)

    def test_logs_distinguish_available_expired_deleted_and_absent_images(self):
        available = self.job()
        expired = self.job(image_expires_at=self.now)
        deleted = self.job(result_image=None, image_deleted_at=self.now)
        missing = self.job(result_image=None)
        pending = self.job(status='queued', result_image=None)
        failed = self.job(status='failed', result_image=None)
        response = self.client.get('/api/v1/admin/ai-renders/')
        rows = {str(row['id']): row['image'] for row in response.data['results']}
        for job, state in ((available, 'available'), (expired, 'expired'), (deleted, 'deleted'), (missing, 'missing'), (pending, 'pending'), (failed, 'none')):
            self.assertEqual(rows[str(job.pk)]['state'], state)
            if state != 'available':
                self.assertIsNone(rows[str(job.pk)]['preview_url'])
                self.assertIsNone(rows[str(job.pk)]['download_url'])
        self.assertEqual(rows[str(available.pk)]['size_bytes'], len(self.png))
        self.assertEqual(rows[str(available.pk)]['download_url'], self.image_url(available)+'?download=1')
        for secret in ('private-prompt', 'owner_hash', 'result_image', 'input_image'):
            self.assertNotIn(secret, response.content.decode())

    def test_cleanup_command_dry_run_and_real_run(self):
        job = self.job(image_expires_at=self.now-timedelta(seconds=1))
        output = StringIO()
        call_command('cleanup_ai_images', dry_run=True, stdout=output)
        self.assertIn('1 generated images due', output.getvalue())
        job.refresh_from_db()
        self.assertIsNotNone(job.result_image)
        call_command('cleanup_ai_images', stdout=StringIO())
        job.refresh_from_db()
        self.assertIsNone(job.result_image)

    def test_dashboard_runs_cleanup_fallback_without_changing_statistics(self):
        job = self.job(image_expires_at=self.now)
        result = self.client.get('/api/v1/admin/ai-usage/')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data['summary']['ready'], 1)
        self.assertEqual(result.data['summary']['costs'][0]['total'], '0.01000000')
        self.assertEqual(result.data['image_retention_days'], 30)
        job.refresh_from_db()
        self.assertIsNone(job.result_image)

    def test_policy_validation_revision_and_permissions(self):
        path = '/api/v1/admin/ai-service/'
        existing = self.job()
        for days in (0, -1, 366, 'invalid', None):
            self.assertEqual(self.client.patch(path, {'revision': 0, 'image_retention_days': days}, format='json').status_code, 400)
        response = self.client.patch(path, {'revision': 0, 'image_retention_days': 7}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['image_retention_days'], 7)
        self.assertEqual(response.data['last_check_status'], 'ok')
        self.assertTrue(response.data['has_api_key'])
        existing.refresh_from_db()
        self.assertEqual(existing.image_expires_at, self.now+timedelta(days=30))
        self.assertEqual(self.client.patch(path, {'revision': 0, 'image_retention_days': 1}, format='json').status_code, 409)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.patch(path, {'revision': 1, 'image_retention_days': 1}, format='json').status_code, 403)
        strict = APIClient(enforce_csrf_checks=True)
        strict.force_login(self.root)
        self.assertEqual(strict.patch(path, {'revision': 1, 'image_retention_days': 1}, format='json').status_code, 403)

    @patch('management_api.ai_generation.edit_image')
    def test_new_result_gets_deadline_from_completion_and_current_policy(self, edit):
        AIServiceConfig.objects.filter(pk=1).update(image_retention_days=7)
        job = self.job(status='queued', result_image=None, image_expires_at=None)
        edit.return_value = (self.png, 'req-example')
        run_render(job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, 'ready')
        self.assertEqual(job.image_expires_at, job.completed_at+timedelta(days=7))
        self.assertFalse(job.input_image)

    def test_legacy_migration_gives_existing_images_thirty_days_from_upgrade(self):
        job = self.job(image_expires_at=None, completed_at=self.now-timedelta(days=365))
        failed = self.job(status='failed', image_expires_at=None, result_image=None)
        migration = importlib.import_module('management_api.migrations.0017_ai_image_retention')
        with patch.object(migration.timezone, 'now', return_value=self.now):
            migration.preserve_existing_images(apps, type('Schema', (), {'connection': connection})())
        job.refresh_from_db()
        failed.refresh_from_db()
        self.assertEqual(job.image_expires_at, self.now+timedelta(days=30))
        self.assertEqual(bytes(job.result_image), self.png)
        self.assertIsNone(failed.image_expires_at)

    def test_customer_endpoint_keeps_ownership_checks_and_reports_expiry(self):
        job = self.job(image_expires_at=self.now)
        customer_client = APIClient()
        session = customer_client.session
        session['store_customer_id'] = str(self.customer.pk)
        session.save()
        path = f'/api/v1/store/ai-renders/{job.pk}/'
        detail = customer_client.get(path)
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(detail.data['imageExpired'])
        self.assertEqual(customer_client.get(path+'image/').status_code, 410)
        other = Customer.objects.create(email='other-image@example.com', verified_at=timezone.now())
        session = customer_client.session
        session['store_customer_id'] = str(other.pk)
        session.save()
        self.assertEqual(customer_client.get(path+'image/').status_code, 404)
