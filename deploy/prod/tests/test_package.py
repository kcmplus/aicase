import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('release_package', Path(__file__).resolve().parents[2] / 'dev/package.py')
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class ProductionPackageTests(unittest.TestCase):
    def test_production_units_are_included_without_dev_units_or_secrets(self):
        for name in ['backup.sh', 'aicase-prod-backup.service', 'aicase-prod-backup.timer',
                     'aicase-prod-ai-cleanup.service', 'aicase-prod-ai-cleanup.timer',
                     'aicase-prod-supplier-orders.service', 'aicase-prod-supplier-orders.timer']:
            self.assertTrue(package.allowed_source('deploy/prod/' + name, 'prod'))
            self.assertFalse(package.allowed_source('deploy/prod/' + name, 'dev'))
        for name in ['deploy/prod/backend.env', 'deploy/prod/backend.env.example',
                     'backend/.env', 'backend/db.sqlite3', 'backend/media/photo.png',
                     'deploy/dev/aicase-dev-ai-cleanup.service']:
            self.assertFalse(package.allowed_source(name, 'prod'))

    def test_unknown_environment_is_rejected_before_building(self):
        with self.assertRaises(ValueError):
            package.build(environment='other')
