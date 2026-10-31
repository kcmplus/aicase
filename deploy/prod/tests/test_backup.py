"""Verify backup failure never publishes or prunes a snapshot."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(sys.platform.startswith('linux'), 'Production runs GNU/Linux')
class BackupTests(unittest.TestCase):
    def test_success_and_failures(self):
        for failure in ['', 'pg_dump', 'pg_restore', 'tar']:
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                state = root / 'state'
                (state / 'daily-backups').mkdir(parents=True)
                env_file = root / 'backend.env'
                env_file.write_text('POSTGRES_USER=test\nPOSTGRES_PASSWORD=test\nPOSTGRES_DB=test\n')
                bindir = root / 'bin'
                bindir.mkdir()
                fake = root / 'fake'
                fake.write_text(f'#!{sys.executable}\n' + '''import os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
with open(os.environ['CALLS'], 'a') as out: out.write(name + '\\n')
if name == os.environ['FAIL']: sys.exit(1)
if name == 'pg_dump': pathlib.Path(sys.argv[-1].split('=',1)[1]).write_text('dump')
if name == 'readlink': print('/opt/aicase-prod/releases/previous')
''')
                fake.chmod(0o755)
                for name in ['pg_dump', 'pg_restore', 'tar', 'readlink', 'find']:
                    (bindir / name).symlink_to(fake)
                script = Path(__file__).resolve().parents[1] / 'backup.sh'
                text = script.read_text().replace('[[ $EUID -eq 0 ]]', 'true')
                text = text.replace('state=/var/lib/aicase-prod', f'state={state}')
                text = text.replace('/etc/aicase-prod/backend.env', str(env_file))
                text = text.replace('/var/lock/aicase-prod-deploy.lock', str(root / 'lock'))
                target = root / 'backup.sh'
                target.write_text(text)
                result = subprocess.run(['bash', str(target)], env={**os.environ,
                    'PATH': f'{bindir}:{os.environ["PATH"]}', 'FAIL': failure, 'CALLS': str(root / 'calls')},
                    text=True, capture_output=True, timeout=10)
                complete = list(state.glob('daily-backups/*/COMPLETE'))
                self.assertEqual(bool(complete), not failure, result.stderr)
                self.assertEqual(result.returncode == 0, not failure, result.stderr)
                self.assertFalse(list(state.glob('daily-backups/*.partial')))
                self.assertEqual('find' in (root / 'calls').read_text(), not failure)
