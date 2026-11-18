"""Verify upgrades from each deployed branch in Django's disposable test database."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class MainDevMigrationTests(TransactionTestCase):
    latest = [('management_api', '0038_merge_social_composition')]

    def upgrade(self, social):
        MigrationExecutor(connection).migrate([('management_api', '0035_merge_v35_dev')])
        try:
            before = [('management_api', '0036_social_login' if social else '0037_ai_composition_regions')]
            executor = MigrationExecutor(connection)
            executor.migrate(before)
            apps = executor.loader.project_state(before).apps
            brand = apps.get_model('management_api', 'Brand').objects.create(code='merge-brand', name='Synthetic')
            model = apps.get_model('management_api', 'PhoneModel').objects.create(
                brand=brand, code='merge-model', name='Preserved', active=False, notes='manual configuration')
            order = apps.get_model('management_api', 'PrintOrder').objects.create(
                model_name=model.name, amount='9.90', currency='USD', status='paid',
                mode='airwallex_live', revision=7, case_material='magnetic', snapshot={'quantity': 1})
            if social:
                customer = apps.get_model('management_api', 'Customer').objects.create(email='merge@example.com', verified_at=timezone.now())
                apps.get_model('management_api', 'SocialLoginConfig').objects.create(
                    provider='google', client_id='preserved-client', secret_ciphertext='synthetic-ciphertext', revision=4)
                apps.get_model('management_api', 'CustomerSocialIdentity').objects.create(
                    customer=customer, provider='google', client_id='preserved-client', subject='preserved-subject')
            else:
                model.composition_regions={'synthetic': 'preserved'}
                model.composition_revision=3
                model.save()
                order.delivery_address={'city':'Synthetic city'}
                order.save()
            order.refresh_from_db()
            expected = {field.attname: getattr(order, field.attname) for field in order._meta.fields}
            executor = MigrationExecutor(connection)
            executor.loader.check_consistent_history(connection)
            self.assertFalse(executor.loader.detect_conflicts())
            executor.migrate(self.latest)
            apps = executor.loader.project_state(self.latest).apps
            migrated = apps.get_model('management_api', 'PrintOrder').objects.get(pk=order.pk)
            self.assertEqual({key:getattr(migrated,key) for key in expected},expected)
            preserved = apps.get_model('management_api', 'PhoneModel').objects.get(pk=model.pk)
            self.assertFalse(preserved.active)
            self.assertEqual(preserved.notes,'manual configuration')
            if social:
                config = apps.get_model('management_api', 'SocialLoginConfig').objects.get(pk='google')
                self.assertEqual((config.client_id,config.secret_ciphertext,config.revision),('preserved-client','synthetic-ciphertext',4))
                identity = apps.get_model('management_api', 'CustomerSocialIdentity').objects.get()
                self.assertEqual((identity.customer_id,identity.subject),(customer.pk,'preserved-subject'))
            else:
                self.assertEqual(preserved.composition_regions,{'synthetic':'preserved'})
                self.assertEqual(preserved.composition_revision,3)
        finally:
            MigrationExecutor(connection).migrate(self.latest)

    def test_upgrade_deployed_dev_preserves_social_identity_and_orders(self):
        self.upgrade(social=True)

    def test_upgrade_main_preserves_delivery_and_composition(self):
        self.upgrade(social=False)
