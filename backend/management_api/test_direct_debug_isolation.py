"""Developer tests for disposable runtime safety; never open a user's database."""
import base64
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import unittest

from django.core.exceptions import ImproperlyConfigured
from config.direct_debug_isolation import isolated_options


class DirectDebugIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='aicase-v35-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = {
            'PATH': os.environ.get('PATH', ''), 'TMPDIR': tempfile.gettempdir(),
            'DIRECT_DEBUG_ISOLATED': '1',
            'DIRECT_DEBUG_ISOLATED_ROOT': str(self.root), 'DJANGO_DEBUG': '1',
            'DJANGO_SECRET_KEY': secrets.token_urlsafe(48),
            'AI_CONFIG_ENCRYPTION_KEY': base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
            'DIRECT_DEBUG_TOKEN': secrets.token_urlsafe(48),
            'DIRECT_DEBUG_DEVICE_ID': '1', 'DIRECT_DEBUG_API_PORT': '18761',
            'DIRECT_DEBUG_H5_ORIGIN': 'http://127.0.0.1:18762',
        }

    def run_child(self, code):
        result = subprocess.run([sys.executable, '-c', code], env=self.env,
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_missing_parameters_fail_before_base_settings_or_local_secrets(self):
        for key in list(self.env):
            if key in ('PATH', 'TMPDIR', 'DIRECT_DEBUG_ISOLATED'):
                continue
            with self.subTest(key=key):
                value = self.env.pop(key)
                try:
                    self.run_child('''
import sys
from django.core.exceptions import ImproperlyConfigured
try:
    import config.direct_debug
except ImproperlyConfigured:
    assert 'config.settings' not in sys.modules
else:
    raise AssertionError('missing isolation option accepted')
''')
                finally:
                    self.env[key] = value

    def test_paths_ports_and_keys_fail_closed(self):
        cases = {
            'DIRECT_DEBUG_ISOLATED_ROOT': ['.', '/tmp', str(self.root / 'missing')],
            'DIRECT_DEBUG_API_PORT': ['8000', '8001', '18762', '0', '65536', 'bad'],
            'DIRECT_DEBUG_H5_ORIGIN': ['https://example.invalid:8888', 'http://127.0.0.1:4173',
                'http://127.0.0.1:18762/path', 'http://user@127.0.0.1:18762', 'http://127.0.0.1:bad'],
            'DIRECT_DEBUG_DEVICE_ID': ['0', '-1', 'bad'],
            'AI_CONFIG_ENCRYPTION_KEY': ['x' * 32], 'DJANGO_DEBUG': ['0'],
            'POSTGRES_DB': ['existing_database'],
        }
        for key, values in cases.items():
            for value in values:
                with self.subTest(key=key, value=value), self.assertRaises(ImproperlyConfigured):
                    isolated_options({**self.env, key: value})

    def test_symlink_and_hardlink_cannot_reach_other_data(self):
        with tempfile.TemporaryDirectory() as other:
            outside = Path(other) / 'sentinel'
            outside.write_text('unchanged')
            link = self.root / 'db.sqlite3'
            link.symlink_to(outside)
            with self.assertRaises(ImproperlyConfigured):
                isolated_options(self.env)
            link.unlink()
            os.link(outside, link)
            with self.assertRaises(ImproperlyConfigured):
                isolated_options(self.env)
            self.assertEqual(outside.read_text(), 'unchanged')

    def test_runtime_uses_only_temp_storage_without_reading_local_credentials(self):
        self.run_child('''
from pathlib import Path
original = Path.read_text
def safe_read(self, *args, **kwargs):
    assert not self.name.startswith('.local-'), 'read local credential'
    return original(self, *args, **kwargs)
Path.read_text = safe_read
import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.direct_debug'
import django
django.setup()
from django.conf import settings
root = Path(os.environ['DIRECT_DEBUG_ISOLATED_ROOT']).resolve()
assert settings.DATABASES['default']['NAME'] == root / 'db.sqlite3'
assert settings.MEDIA_ROOT == root / 'media'
assert settings.DIRECT_DEBUG_ENABLED
assert not settings.SUPPLIER_ORDER_ENABLED and not settings.SUPPLIER_PAYMENT_ENABLED
from django.core.management import call_command
call_command('migrate', verbosity=0, interactive=False)
from django.db import connection
assert 'management_api_printorder' in connection.introspection.table_names()
from django.test import Client
assert Client().get('/api/health/').status_code == 200
''')
        self.assertTrue((self.root / 'db.sqlite3').exists())

    def test_network_is_blocked_before_resolution_or_connect(self):
        self.run_child('''
import config.direct_debug
import socket
operations = [lambda: socket.getaddrinfo('example.invalid', 443),
    lambda: socket.gethostbyname('example.invalid'),
    lambda: socket.create_connection(('127.0.0.1', 1))]
with socket.socket() as s:
    operations += [lambda: s.connect(('192.0.2.1', 443)),
                   lambda: s.connect_ex(('192.0.2.1', 443)),
                   lambda: s.sendto(b'test', ('192.0.2.1', 443))]
    for operation in operations:
        try:
            operation()
        except OSError as exc:
            assert 'disabled in isolated' in str(exc)
        else:
            raise AssertionError('outbound operation allowed')
assert socket.getaddrinfo('127.0.0.1', 18761)
''')

    def test_migration_and_service_process_share_only_disposable_database(self):
        self.run_child('''
import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.direct_debug'
import django
django.setup()
from django.core.management import call_command
call_command('migrate', verbosity=0, interactive=False)
from django.contrib.auth.models import Group
Group.objects.create(name='synthetic-isolation-sentinel')
''')
        self.run_child('''
import os
from pathlib import Path
original = Path.read_text
def no_local_credentials(self, *args, **kwargs):
    assert not self.name.startswith('.local-'), 'read local credential'
    return original(self, *args, **kwargs)
Path.read_text = no_local_credentials
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.direct_debug'
import django
django.setup()
from django.contrib.auth.models import Group
from django.db import connection
assert Group.objects.get(name='synthetic-isolation-sentinel')
assert Path(connection.settings_dict['NAME']).resolve().parent == Path(os.environ['DIRECT_DEBUG_ISOLATED_ROOT']).resolve()
from django.conf import settings
assert settings.MEDIA_ROOT.parent == Path(os.environ['DIRECT_DEBUG_ISOLATED_ROOT']).resolve()
assert settings.STATIC_ROOT.parent == settings.MEDIA_ROOT.parent
assert settings.EMAIL_BACKEND == 'django.core.mail.backends.locmem.EmailBackend'
from django.test import Client
assert Client().get('/api/health/').status_code == 200
''')

    def test_default_branch_unchanged_without_opening_existing_database_or_token(self):
        self.env.pop('DIRECT_DEBUG_ISOLATED')
        self.run_child('''
from pathlib import Path
original = Path.read_text
reads = []
def synthetic_token(self, *args, **kwargs):
    if self.name.startswith('.local-'):
        assert self.name == '.local-direct-debug-token'
        reads.append(self.name)
        return 'synthetic-default-token-for-qa-only'
    return original(self, *args, **kwargs)
Path.read_text = synthetic_token
import config.direct_debug as settings
assert settings.DATABASES['default']['NAME'] == settings.BASE_DIR / '.direct-debug.sqlite3'
assert settings.DIRECT_DEBUG_TOKEN == 'synthetic-default-token-for-qa-only'
assert reads == ['.local-direct-debug-token']
assert settings.DIRECT_DEBUG_ENABLED
assert not settings.SUPPLIER_ORDER_ENABLED and not settings.SUPPLIER_PAYMENT_ENABLED
''')

    def test_invalid_isolation_flag_fails_before_loading_settings(self):
        for value in ('true', 'yes', '', '2'):
            with self.subTest(value=value):
                self.env['DIRECT_DEBUG_ISOLATED'] = value
                self.run_child('''
import sys
from django.core.exceptions import ImproperlyConfigured
try:
    import config.direct_debug
except ImproperlyConfigured:
    assert 'config.settings' not in sys.modules
else:
    raise AssertionError('invalid isolation flag accepted')
''')

    def test_udp_sendmsg_is_also_blocked(self):
        # Instrument the transport boundary: no bind/send syscall or external I/O.
        self.run_child('''
import socket
from unittest.mock import patch
assert hasattr(socket.socket, 'sendmsg'), 'platform needs sendmsg coverage'
with patch.object(socket.socket, 'sendmsg', return_value=21) as transport:
    import config.direct_debug
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
        try:
            sender.sendmsg([b'synthetic-qa-datagram'], [], 0, ('127.0.0.1', 9))
        except OSError as exc:
            assert 'disabled in isolated' in str(exc), str(exc)
        else:
            raise AssertionError('isolated UDP sendmsg reached the transport instead of being blocked')
    transport.assert_not_called()
''')
