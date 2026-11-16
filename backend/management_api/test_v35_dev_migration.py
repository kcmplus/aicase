"""Upgrade both branch histories using only Django's disposable test database."""
from importlib import import_module
from unittest.mock import patch

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class V35DevMigrationTests(TransactionTestCase):
    def upgrade_history(self, *, ui):
        latest = [('management_api', '0035_merge_v35_dev')]
        base = [('management_api', '0030_supplier_retry_and_image_urls')]
        location = import_module('management_api.migrations.0032_device_location_sync').Migration
        old_dependencies = [('management_api', '0031_direct_debug_transport' if ui else '0031_supplier_catalog_auto_publish')]
        before = [('management_api', '0034_phone_color_previews' if ui else '0033_order_case_material')]
        MigrationExecutor(connection).migrate(base)
        try:
            # Reconstruct the actual graph at each branch head, including UI's
            # former location dependency. No fake-applied migrations are used.
            with patch.object(location, 'dependencies', old_dependencies):
                executor = MigrationExecutor(connection)
                executor.migrate(before)
                apps = executor.loader.project_state(before).apps
                Brand = apps.get_model('management_api', 'Brand')
                Model = apps.get_model('management_api', 'PhoneModel')
                Order = apps.get_model('management_api', 'PrintOrder')
                brand = Brand.objects.create(code='preserved-brand', name='Synthetic')
                model = Model.objects.create(brand=brand, code='preserved-model', name='Preserved',
                    active=False, notes='manual mapping must remain')
                kwargs = {} if ui else {'case_material': 'magnetic'}
                order = Order.objects.create(model_name=model.name, amount='29.70', currency='USD',
                    status='paid', mode='airwallex_live', revision=7,
                    snapshot={'quantity': 3, 'photo': 'synthetic-private-placeholder'}, **kwargs)
                order.refresh_from_db()
                expected = {f.attname: getattr(order, f.attname) for f in Order._meta.fields}
                if ui:
                    Color = apps.get_model('management_api', 'PhoneColor')
                    color = Color.objects.create(phone_model=model, code='saved', name='Saved',
                        rgb={'r': 1, 'g': 2, 'b': 3}, active=False)
            executor = MigrationExecutor(connection)
            executor.loader.check_consistent_history(connection)
            self.assertFalse(executor.loader.detect_conflicts())
            executor.migrate(latest)
            apps = executor.loader.project_state(latest).apps
            migrated = apps.get_model('management_api', 'PrintOrder').objects.get(pk=order.pk)
            self.assertEqual({key: getattr(migrated, key) for key in expected}, expected)
            self.assertEqual(migrated.case_material, '' if ui else 'magnetic')
            model = apps.get_model('management_api', 'PhoneModel').objects.get(pk=model.pk)
            self.assertFalse(model.active)
            self.assertEqual(model.notes, 'manual mapping must remain')
            if ui:
                saved = apps.get_model('management_api', 'PhoneColor').objects.get(pk=color.pk)
                self.assertEqual(saved.rgb, {'r': 1, 'g': 2, 'b': 3})
                self.assertFalse(saved.active)
            self.assertIn('transport', {f.name for f in apps.get_model('management_api', 'SupplierOrder')._meta.fields})
        finally:
            MigrationExecutor(connection).migrate(latest)

    def test_upgrade_deployed_dev_preserves_orders_and_manual_models(self):
        self.upgrade_history(ui=False)

    def test_upgrade_v35_preserves_colors_and_historical_paid_snapshots(self):
        self.upgrade_history(ui=True)
