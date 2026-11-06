from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone
import uuid


class FulfillmentMigrationTests(TransactionTestCase):
    def test_old_orders_stay_unclassified_and_old_claims_are_not_replayed(self):
        before = [('management_api', '0024_terminal_print_release')]
        after = MigrationExecutor(connection).loader.graph.leaf_nodes('management_api')
        executor = MigrationExecutor(connection)
        executor.migrate(before)
        try:
            apps = executor.loader.project_state(before).apps
            order = apps.get_model('management_api', 'PrintOrder').objects.create(
                model_name='Historical phone', amount='10.00', mode='airwallex_live', status='paid')
            vendor = apps.get_model('management_api', 'DeviceProviderConnection').objects.create(
                name='Historical connection', shop_id='146', base_url='https://shop.widermatrix.cn')
            device = apps.get_model('management_api', 'Device').objects.create(
                connection=vendor, vendor_device_id='401', name='Historical device')
            credential = apps.get_model('management_api', 'TerminalCredential').objects.create(
                device=device, token_hash='a'*64, active=True)
            product = apps.get_model('management_api', 'SupplierProduct').objects.create(
                connection=vendor, goods_id='17', product_id='1', name='Historical case')
            stock = apps.get_model('management_api', 'DeviceProduct').objects.create(
                device=device, product=product, observed_at=timezone.now())
            claim = uuid.uuid4()
            row = apps.get_model('management_api', 'SupplierOrder').objects.create(
                order=order, device=device, inventory_item=stock, business_number='1793786316892802680',
                goods_id=17, order_revision=1, snapshot_sha256='b'*64, state='submitted', trade_no='HISTORY1',
                print_confirmed_at=timezone.now(), release_state='unknown', release_claim=claim)
            executor = MigrationExecutor(connection)
            executor.migrate(after)
            apps = executor.loader.project_state(after).apps
            migrated = apps.get_model('management_api', 'PrintOrder').objects.get(pk=order.pk)
            self.assertEqual(migrated.fulfillment_type, 'unspecified')
            self.assertEqual(migrated.status, 'paid')
            self.assertFalse(apps.get_model('management_api', 'TerminalCredential').objects.get(pk=credential.pk).active)
            history = apps.get_model('management_api', 'SupplierOrder').objects.get(pk=row.pk)
            self.assertEqual(history.release_state, 'unknown')
            self.assertEqual(history.release_claim, claim)
            self.assertEqual(history.state, 'submitted')
            self.assertIsNotNone(history.print_confirmed_at)
        finally:
            MigrationExecutor(connection).migrate(after)
