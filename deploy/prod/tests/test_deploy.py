"""Exercise release switching and failure recovery with isolated fake services."""
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(sys.platform.startswith('linux'), 'Deployment targets GNU/Linux')
class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / 'app'
        self.state = self.root / 'state'
        self.state.mkdir()
        (self.state / 'media').mkdir()
        self.base.mkdir()
        (self.root / 'units').mkdir()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.release_id = '1-1-' + 'a' * 40
        self.release = self.base / 'releases' / self.release_id
        self.env = {**os.environ, 'PATH': f'{self.bin}:{os.environ["PATH"]}',
                    'TEST_ROOT': str(self.root), 'TEST_FAIL': ''}
        env_file = self.root / 'backend.env'
        env_file.write_text(f'DJANGO_SECRET_KEY=test\nAI_CONFIG_ENCRYPTION_KEY=test\nPOSTGRES_DB=test\nPOSTGRES_USER=test\nPOSTGRES_PASSWORD=test\nDJANGO_DEBUG=0\nDJANGO_TRUST_PROXY=1\nDJANGO_MEDIA_ROOT={self.state}/media\n')
        # Only replace absolute host paths and the root check. All deployment logic
        # (traps, backup ordering, seeding, symlink switch, rollback) runs unchanged.
        source = (Path(__file__).resolve().parents[1] / 'deploy.sh').read_text()
        source = source.replace('[[ $EUID -eq 0 ]]', 'true')
        for name in ['fullchain.pem', 'privkey.pem']:
            source = source.replace('/etc/letsencrypt/live/popomo.chunpat.cc/' + name, str(env_file))
        source = source.replace('base=/opt/aicase-prod', f'base={self.base}')
        source = source.replace('unit_dir=/etc/systemd/system', f'unit_dir={self.root / "units"}')
        source = source.replace('state=/var/lib/aicase-prod', f'state={self.state}')
        source = source.replace('env_file=/etc/aicase-prod/backend.env', f'env_file={env_file}')
        source = source.replace('/var/lock/aicase-prod-deploy.lock', str(self.root / 'lock'))
        source = source.replace('/usr/local/sbin/aicase-prod-backup', str(self.root / 'backup-program'))
        self.script = self.root / 'deploy.sh'
        self.script.write_text(source)
        self.fake = self.root / 'fake.py'
        self.fake.write_text('''import os, pathlib, sys
root = pathlib.Path(os.environ['TEST_ROOT'])
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with (root / 'calls').open('a') as log: log.write(name + ' ' + ' '.join(args) + '\\n')
fail = os.environ.get('TEST_FAIL', '')
if name == 'python3':
    target = pathlib.Path(args[-1]) / 'bin'
    target.mkdir(parents=True)
    (target / 'python').symlink_to(root / 'fake-executable')
elif name == 'runuser':
    os.execv(args[3], args[3:])
elif name == 'python' and len(args) > 1 and args[1] == 'shell':
    print('0')
elif name == 'python' and len(args) > 1 and args[1] == 'collectstatic':
    (pathlib.Path(args[0]).parent / 'staticfiles').mkdir()
elif name == 'python' and len(args) > 1 and args[1] == 'migrate' and fail == 'migrate':
    sys.exit(1)
elif name == 'pg_dump':
    if fail == 'backup': sys.exit(1)
    pathlib.Path(args[-1].split('=',1)[1]).write_text('backup')
elif name == 'pg_restore' and fail == 'backup-verification':
    sys.exit(1)
elif name == 'curl' and fail == 'health':
    if (root / 'app/current').resolve().name != 'previous': sys.exit(22)
''')
        executable = self.root / 'fake-executable'
        executable.write_text(f'#!{sys.executable}\n' + self.fake.read_text())
        executable.chmod(0o755)
        for name in ['python3', 'id', 'runuser', 'chown', 'systemctl', 'curl', 'sleep', 'pg_dump', 'pg_restore', 'nginx']:
            (self.bin / name).symlink_to(executable)
        tree = self.root / 'payload'
        (tree / 'backend').mkdir(parents=True)
        (tree / 'backend/manage.py').write_text('# placeholder')
        (tree / 'backend/requirements.txt').write_text('')
        (tree / 'frontend/storefront').mkdir(parents=True)
        (tree / 'frontend/storefront/index.html').write_text('test')
        (tree / 'VERSION').write_text('a' * 40 + '\n')
        (tree / 'deploy/prod').mkdir(parents=True)
        for name in ['aicase-prod-ai-cleanup.service', 'aicase-prod-ai-cleanup.timer', 'aicase-prod-backup.service', 'aicase-prod-backup.timer', 'backup.sh', 'aicase-prod-supplier-orders.service', 'aicase-prod-supplier-orders.timer', 'aicase-prod-inventory.service', 'aicase-prod-inventory.timer']:
            shutil.copyfile(Path(__file__).resolve().parents[1] / name, tree / 'deploy/prod' / name)
        with tarfile.open(self.root / 'release.tar.gz', 'w:gz') as archive:
            for path in tree.iterdir(): archive.add(path, arcname=path.name)

    def previous_release(self):
        previous = self.base / 'releases/previous'
        (previous / 'backend').mkdir(parents=True)
        (previous / 'backend/manage.py').write_text('# previous')
        (previous / '.venv/bin').mkdir(parents=True)
        (previous / '.venv/bin/python').symlink_to(self.root / 'fake-executable')
        (self.base / 'current').symlink_to(previous)
        return previous

    def run_deploy(self, fail=''):
        self.env['TEST_FAIL'] = fail
        return subprocess.run(['bash', str(self.script), self.release_id], cwd=self.root,
                              env=self.env, capture_output=True, text=True, timeout=15)

    def test_first_release_seeds_and_publishes_after_backup(self):
        result = self.run_deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.base / 'current').resolve(), self.release)
        self.assertFalse((self.state / 'deploying').exists())
        calls = (self.root / 'calls').read_text()
        self.assertIn('seed_phone_templates --only-supplied', calls)
        self.assertIn('systemctl enable --now aicase-prod-ai-cleanup.timer', calls)
        self.assertIn('systemctl enable --now aicase-prod-backup.timer', calls)
        self.assertIn('systemctl enable --now aicase-prod-inventory.timer', calls)
        self.assertTrue((self.root / 'units/aicase-prod-inventory.service').exists())
        self.assertLess(calls.index('pg_restore '), calls.index('migrate --noinput'))
        self.assertTrue((self.root / 'units/aicase-prod-ai-cleanup.service').exists())
        self.assertLess(calls.index('pg_dump '), calls.index('migrate --noinput'))
        self.assertTrue((self.state / 'backups' / self.release_id / 'COMPLETE').exists())

    def test_upgrade_preserves_managed_catalog(self):
        self.previous_release()
        (self.root / 'units/aicase-prod-inventory.service').write_text('existing')
        result = self.run_deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = (self.root / 'calls').read_text()
        self.assertNotIn('seed_catalog', calls)
        self.assertLess(calls.index('systemctl stop aicase-prod-inventory.service'), calls.index('pg_dump '))

    def test_failures_restore_previous_release(self):
        previous = self.previous_release()
        for failure in ['backup', 'backup-verification', 'migrate', 'health']:
            with self.subTest(failure=failure):
                result = self.run_deploy(failure)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((self.base / 'current').resolve(), previous)
                self.assertFalse((self.state / 'deploying').exists(), result.stderr)
                self.assertIn('restoring the previous', result.stderr)
                shutil.rmtree(self.release)
                shutil.rmtree(self.state / 'backups' / self.release_id)

    def test_failed_first_release_stays_in_maintenance(self):
        result = self.run_deploy('health')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.base / 'current').exists())
        self.assertTrue((self.state / 'deploying').exists())
