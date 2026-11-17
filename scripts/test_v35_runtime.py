"""Developer lifecycle tests; use only new temporary databases and loopback."""
import os
import socket
import sqlite3
import unittest
from unittest.mock import patch
from urllib.request import build_opener, ProxyHandler

from v35_runtime import IsolatedRuntime


class RuntimeTests(unittest.TestCase):
    def test_real_http_new_database_environment_and_cleanup(self):
        runtime = IsolatedRuntime()
        with patch.dict(os.environ, {'POSTGRES_DB': 'must-not-read', 'NODE_OPTIONS': '--invalid',
                                     'DIRECT_DEBUG_TOKEN': 'must-not-inherit'}):
            with runtime:
                root = runtime.root
                ports = runtime.api_port, runtime.h5_port
                self.assertNotIn('POSTGRES_DB', runtime.env)
                self.assertNotIn('NODE_OPTIONS', runtime.env)
                self.assertNotEqual(runtime.env['DIRECT_DEBUG_TOKEN'], 'must-not-inherit')
                with sqlite3.connect(root / 'db.sqlite3') as db:
                    self.assertGreater(db.execute('SELECT COUNT(*) FROM django_migrations').fetchone()[0], 0)
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM management_api_printorder').fetchone()[0], 0)
                opener = build_opener(ProxyHandler({}))
                with opener.open(runtime.h5_origin + '/api/health/') as response:
                    self.assertIn(b'"ok"', response.read())
                with opener.open(runtime.h5_origin + '/') as response:
                    self.assertIn(b'simple-app.js', response.read())
        self.assertFalse(root.exists())
        self.assertIsNone(runtime.env)
        self.assertTrue(all(child.poll() is not None for child in runtime.children))
        for port in ports:
            with socket.socket() as sock:
                self.assertNotEqual(sock.connect_ex(('127.0.0.1', port)), 0)

    def test_occupied_port_is_not_used_or_killed(self):
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1', 0))
            occupied.listen()
            runtime = IsolatedRuntime(api_port=occupied.getsockname()[1])
            with self.assertRaises(OSError):
                runtime.__enter__()
            self.assertIsNone(runtime.root)
            self.assertEqual(runtime.children, [])
            self.assertGreaterEqual(occupied.fileno(), 0)

    def test_defaults_and_duplicate_ports_rejected(self):
        for port in (8000, 8001, 4173, 4174, 5173, -1, 65536):
            with self.subTest(port=port), self.assertRaises(ValueError):
                with IsolatedRuntime(api_port=port):
                    self.fail('accepted unsafe port')
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        with self.assertRaises(OSError):
            with IsolatedRuntime(port, port):
                self.fail('accepted duplicate port')

    def test_partial_start_failure_cleans_running_child_and_database(self):
        runtime = IsolatedRuntime()
        with patch.object(runtime, '_ready', side_effect=RuntimeError('injected readiness failure')):
            with self.assertRaises(RuntimeError):
                runtime.__enter__()
        self.assertFalse(runtime.root.exists())
        self.assertTrue(all(child.poll() is not None for child in runtime.children))

    def test_body_failure_also_cleans(self):
        runtime = IsolatedRuntime()
        with self.assertRaisesRegex(RuntimeError, 'consumer failure'):
            with runtime:
                raise RuntimeError('consumer failure')
        self.assertFalse(runtime.root.exists())
        self.assertTrue(all(child.poll() is not None for child in runtime.children))


if __name__ == '__main__':
    unittest.main()
