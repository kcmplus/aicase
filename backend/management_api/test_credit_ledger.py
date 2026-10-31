import hashlib
import uuid
from datetime import timedelta
from unittest.mock import patch
from django.apps import apps
from django.contrib.auth.models import User
from django.db import connection, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from .models import Customer, AIAccount, CreditEntry, AIRender, PricingPlan
from .credit_ledger import record, ensure_opening
from .ai_generation import refresh_account, restore_credit


class CreditLedgerTests(TestCase):
    def setUp(self):
        self.customer=Customer.objects.create(email='ledger@example.com',verified_at=timezone.now())
        self.account=AIAccount.objects.create(customer=self.customer,owner_hash=hashlib.sha256(('customer:'+str(self.customer.pk)).encode()).hexdigest(),trial_granted=3,trial_used=1)
        self.admin=User.objects.create_superuser('ledger-admin',password='test-only-password')
        self.admin_client=APIClient();self.admin_client.force_authenticate(self.admin)
        self.client=APIClient();session=self.client.session;session['store_customer_id']=str(self.customer.pk);session.save()
        self.url=f'/api/v1/admin/customers/{self.customer.pk}/'

    def test_grant_transaction_has_exact_balances_and_private_reason(self):
        body={'revision':0,'amount':4,'reason':'Private compensation investigation'}
        response=self.admin_client.post(self.url+'grant/',body,format='json')
        self.assertEqual(response.status_code,200,response.data)
        rows=list(CreditEntry.objects.order_by('id'))
        self.assertEqual([(r.kind,r.amount,r.balance_before,r.balance_after) for r in rows],[('opening',2,0,2),('grant',4,2,6)])
        self.assertEqual(self.admin_client.post(self.url+'grant/',body,format='json').status_code,409)
        self.assertEqual(CreditEntry.objects.filter(kind='grant').count(),1)
        own=self.client.get('/api/v1/store/customer/credits/');self.assertEqual(own.status_code,200)
        self.assertNotIn('Private compensation',str(own.data));self.assertNotIn('actorName',str(own.data))
        staff=self.admin_client.get(self.url+'credits/');self.assertIn('Private compensation',str(staff.data))
        self.assertEqual(self.client.get(self.url+'credits/').status_code,403)
        self.client.delete('/api/v1/store/customer/')
        self.assertEqual(self.client.get('/api/v1/store/customer/credits/').status_code,403)

    def test_ledger_failure_rolls_back_grant_and_revision(self):
        with patch('management_api.customers.record',side_effect=RuntimeError('ledger unavailable')):
            with self.assertRaises(RuntimeError):self.admin_client.post(self.url+'grant/',{'revision':0,'amount':2,'reason':'Support'},format='json')
        self.account.refresh_from_db();self.customer.refresh_from_db()
        self.assertEqual(self.account.bonus_granted,0);self.assertEqual(self.customer.revision,0)
        self.assertFalse(CreditEntry.objects.exists())

    def test_cursor_is_stable_and_cannot_read_another_account(self):
        for i in range(25):record(self.account,f'test:{i}','grant','gift',i,i+1)
        other=AIAccount.objects.create(owner_hash='x'*64)
        record(other,'other','grant','gift',0,999)
        first=self.client.get('/api/v1/store/customer/credits/').data
        self.assertEqual(len(first['results']),20);self.assertIsNotNone(first['nextCursor'])
        record(self.account,'new','grant','gift',25,26)
        second=self.client.get('/api/v1/store/customer/credits/',{'before':first['nextCursor']}).data
        self.assertEqual(len(second['results']),5);self.assertIsNone(second['nextCursor'])
        ids={r['id'] for r in first['results']};self.assertFalse(ids.intersection(r['id'] for r in second['results']))
        self.assertNotIn(999,[r['balanceAfter'] for r in first['results']+second['results']])
        self.assertEqual(self.client.get('/api/v1/store/customer/credits/?before=bad').status_code,400)

    def subscription(self, expired=True, renew=False):
        start=int((timezone.now()-timedelta(days=35)).timestamp()*1000)
        end=int((timezone.now()+timedelta(days=-1 if expired else 1)).timestamp()*1000)
        self.account.subscription={'anchor':start,'cycle':0,'startsAt':start,'endsAt':end,'monthlyLimit':10,'used':3,'renew':renew}
        self.account.save();return start

    def job(self, period):
        return AIRender.objects.create(owner_hash=self.account.pk,request_key=uuid.uuid4(),input_image=b'',allocation={'type':'monthly','period':period})

    def test_monthly_expiry_and_renewal_are_once_per_period(self):
        start=self.subscription(renew=True)
        plan=PricingPlan.objects.create(code='ledger-plan',name='Monthly',kind='ai_monthly',price='5.99',monthly_credits=12)
        plan.refresh_from_db()
        refresh_account(self.account,plan);refresh_account(self.account,plan)
        self.assertEqual(CreditEntry.objects.get(kind='expiry').amount,-7)
        self.assertEqual(CreditEntry.objects.get(kind='renewal').amount,12)
        self.assertEqual(self.account.subscription['used'],0)
        job=self.job(start);restore_credit(job,'failed');restore_credit(job,'failed')
        entry=CreditEntry.objects.get(kind='refund_expired');self.assertEqual(entry.amount,0);self.assertEqual(entry.balance_after,12)
        job.refresh_from_db();self.assertFalse(job.credit_restored)

    def test_monthly_refund_in_current_period_is_once(self):
        period=self.subscription(expired=False)
        job=self.job(period);restore_credit(job,'cancelled');restore_credit(job,'cancelled')
        entry=CreditEntry.objects.get(kind='cancel_refund');self.assertEqual((entry.amount,entry.balance_before,entry.balance_after),(1,7,8))
        self.account.refresh_from_db();self.assertEqual(self.account.subscription['used'],2)

    def test_migration_snapshot_preserves_balances_without_inventing_history(self):
        import importlib
        self.subscription(expired=True)
        migration=importlib.import_module('management_api.migrations.0013_credit_ledger')
        # Run the migration data function against this isolated test database.
        class Editor:connection=connection
        migration.opening_balances(apps,Editor())
        rows=list(CreditEntry.objects.order_by('id'))
        self.assertEqual([(r.pool,r.kind,r.amount) for r in rows],[('gift','opening',2),('monthly','opening',0)])
        self.account.refresh_from_db();self.assertEqual(self.account.trial_used,1)
        refresh_account(self.account,None)
        self.assertFalse(CreditEntry.objects.filter(kind='expiry').exists())
