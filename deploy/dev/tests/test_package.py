import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('release_package', Path(__file__).resolve().parents[1] / 'package.py')
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class ReleaseBoundaryTests(unittest.TestCase):
    def test_private_runtime_files_never_enter_release(self):
        for name in ['backend/.env', 'backend/.env.example', 'backend/.local-secret',
                     'backend/.local-ai-encryption-key', 'backend/.venv/bin/python',
                     'backend/db.sqlite3', 'backend/db.sqlite3-wal',
                     'backend/media/private.png', 'backend/service.key',
                     'frontend/storefront/.env', '.git/config', 'test-results/screen.png']:
            with self.subTest(name=name):
                self.assertFalse(package.allowed_source(name))

    def test_runtime_and_seed_assets_are_kept(self):
        for name in ['backend/manage.py', 'backend/requirements.txt',
                     'deploy/dev/aicase-dev-ai-cleanup.service', 'deploy/dev/aicase-dev-ai-cleanup.timer',
                     'backend/management_api/migrations/0008_ai_render.py',
                     'backend/management_api/seed/catalog.json',
                     'frontend/storefront/device.html',
                     'frontend/storefront/assets/phone-templates/iphone17.png']:
            with self.subTest(name=name):
                self.assertTrue(package.allowed_source(name))
