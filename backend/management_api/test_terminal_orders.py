"""Old terminal clients must never mutate or release an order after retirement."""
import hashlib
import json
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings

from .models import TerminalCredential
from . import test_supplier_orders as supplier_tests


@override_settings(SUPPLIER_ORDER_ENABLED=True, SUPPLIER_PRINT_RELEASE_ENABLED=True)
class RetiredTerminalTests(TestCase):
    setUp = supplier_tests.SupplierOrderTests.setUp
    post = supplier_tests.SupplierOrderTests.post
    bind = supplier_tests.SupplierOrderTests.bind
    image = supplier_tests.SupplierOrderTests.image
    prepare = supplier_tests.SupplierOrderTests.prepare
    pay = supplier_tests.SupplierOrderTests.pay

    def ready(self):
        row = self.prepare()
        self.pay()
        row.state, row.trade_no, row.vendor_id = 'submitted', 'TRADE1', '1'
        row.save()
        return row

    def test_old_credentials_and_origins_cannot_read_claim_or_report(self):
        row = self.ready()
        TerminalCredential.objects.create(device=self.device, token_hash=hashlib.sha256(b'old-token').hexdigest())
        headers = {'HTTP_AUTHORIZATION': 'Bearer old-token', 'HTTP_X_DEVICE_ID': '401',
                   'HTTP_X_SHOP_ID': '146', 'HTTP_ORIGIN': 'tauri://localhost'}
        urls = ['/api/v1/terminal/orders/',
                f'/api/v1/terminal/orders/{self.order.reference}/claim/',
                f'/api/v1/terminal/orders/{self.order.reference}/observe/']
        for url in urls:
            for method in ('get', 'post', 'options'):
                response = getattr(self.client, method)(url, **headers)
                self.assertEqual(response.status_code, 410)
                self.assertNotIn('Access-Control-Allow-Origin', response)
                self.assertIn('no-store', response['Cache-Control'])
        row.refresh_from_db()
        self.assertEqual(row.release_state, 'idle')
        self.assertIsNone(row.print_confirmed_at)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'paid')

    def test_retired_rotation_creates_no_key_and_does_not_reset_history(self):
        output = StringIO()
        with self.assertRaises(CommandError):
            call_command('rotate_terminal_credential', str(self.device.pk), stdout=output)
        self.assertFalse(TerminalCredential.objects.exists())
        self.assertEqual(output.getvalue(), '')

    @patch('management_api.refunds.reconcile')
    def test_historical_claims_still_block_refund_until_manually_verified(self, reconcile):
        from django.utils import timezone
        row = self.ready()
        row.print_confirmed_at, row.release_state = timezone.now(), 'unknown'
        row.save()
        self.order.airwallex_payment_intent = 'int_paid'
        self.order.save()
        admin = get_user_model().objects.create_superuser('admin-refund', password='local-test-only')
        self.client.force_login(admin)
        response = self.client.post(f'/api/v1/admin/orders/{self.order.pk}/refund/',
            json.dumps({'revision': self.order.revision, 'confirmed': True, 'reason': 'requested_by_customer'}),
            content_type='application/json')
        self.assertEqual(response.status_code, 409)
        reconcile.assert_not_called()
        row.refresh_from_db()
        self.assertEqual(row.release_state, 'unknown')
