from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone
import uuid


class FulfillmentMigrationTests(TransactionTestCase):
    def test_old_orders_default_to_pickup_without_replaying_old_claims(self):
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
            self.assertEqual(migrated.fulfillment_type, 'pickup')
            self.assertEqual(migrated.status, 'paid')
            self.assertFalse(apps.get_model('management_api', 'TerminalCredential').objects.get(pk=credential.pk).active)
            history = apps.get_model('management_api', 'SupplierOrder').objects.get(pk=row.pk)
            self.assertEqual(history.release_state, 'unknown')
            self.assertEqual(history.release_claim, claim)
            self.assertEqual(history.state, 'submitted')
            self.assertIsNotNone(history.print_confirmed_at)
        finally:
            MigrationExecutor(connection).migrate(after)


class DefaultPickupMigrationTests(TransactionTestCase):
    def test_only_unclassified_delivery_is_changed_without_touching_order_history(self):
        before = [('management_api', '0027_supplier_payment_currency')]
        after = MigrationExecutor(connection).loader.graph.leaf_nodes('management_api')
        executor = MigrationExecutor(connection)
        executor.migrate(before)
        try:
            Order = executor.loader.project_state(before).apps.get_model('management_api', 'PrintOrder')
            ids = []
            for delivery in ['unspecified', 'pickup', 'courier', 'air']:
                for status in ['pending', 'paid', 'cancelled', 'printing', 'ready', 'completed']:
                    ids.append(Order.objects.create(fulfillment_type=delivery, status=status,
                        model_name='Historical phone', amount='0.50', revision=7,
                        station_id='401' if status == 'printing' else '').pk)
            snapshots = {o.pk: {f.attname: getattr(o, f.attname) for f in o._meta.fields}
                         for o in Order.objects.filter(pk__in=ids)}
            executor = MigrationExecutor(connection)
            executor.migrate(after)
            Order = executor.loader.project_state(after).apps.get_model('management_api', 'PrintOrder')
            for order in Order.objects.filter(pk__in=ids):
                expected = snapshots[order.pk]
                if expected['fulfillment_type'] == 'unspecified':
                    expected['fulfillment_type'] = 'pickup'
                self.assertEqual({f.attname: getattr(order, f.attname) for f in order._meta.fields}, expected)
            self.assertEqual(Order.objects.create(model_name='New phone', amount='0.50').fulfillment_type, 'pickup')
        finally:
            MigrationExecutor(connection).migrate(after)
