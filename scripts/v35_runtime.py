"""Disposable local services for V35 development; no user database or credentials."""
import base64
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parents[1]


class IsolatedRuntime:
    """Own all child processes and temporary files, including partial startup failures.

    This starts an empty migrated database. Browser isolation and synthetic business
    fixtures belong to the caller; this is not the whole-site acceptance runner.
    """
    def __init__(self, api_port=0, h5_port=0):
        self.requested_ports = (api_port, h5_port)
        self.children = []
        self.reservations = []
        self.files = []
        self.temp = None
        self.root = None
        self.env = None

    def _reserve(self, port):
        if port and (not 1024 <= port <= 65535 or port in (8000, 8001, 4173, 4174, 5173)):
            raise ValueError('Use dedicated non-default local ports.')
        sock = socket.socket()
        self.reservations.append(sock)
        sock.bind(('127.0.0.1', port))
        return sock, sock.getsockname()[1]

    def _spawn(self, argv, name, env):
        output = open(self.root / f'{name}.log', 'wb')
        self.files.append(output)
        child = subprocess.Popen(argv, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                 stdout=output, stderr=subprocess.STDOUT)
        self.children.append(child)
        return child

    def _ready(self, url, child, expected, timeout=20):
        opener = build_opener(ProxyHandler({}))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise RuntimeError('Isolated service exited before readiness.')
            try:
                with opener.open(url, timeout=0.5) as response:
                    if response.status == 200 and expected in response.read():
                        return
            except OSError:
                pass
            time.sleep(0.05)
        raise RuntimeError('Isolated service readiness timed out.')

    def __enter__(self):
        try:
            api_socket, self.api_port = self._reserve(self.requested_ports[0])
            h5_socket, self.h5_port = self._reserve(self.requested_ports[1])
            self.api_origin = f'http://127.0.0.1:{self.api_port}'
            self.h5_origin = f'http://127.0.0.1:{self.h5_port}'
            self.temp = tempfile.TemporaryDirectory(prefix='aicase-v35-')
            self.root = Path(self.temp.name).resolve()
            # Whitelist environment: never inherit database, payment, proxy,
            # Python import hooks or Node preload options from the calling shell.
            self.env = {
                'PATH': os.environ.get('PATH', ''), 'TMPDIR': tempfile.gettempdir(),
                'DJANGO_SETTINGS_MODULE': 'config.direct_debug', 'DJANGO_DEBUG': '1',
                'DIRECT_DEBUG_ISOLATED': '1', 'DIRECT_DEBUG_ISOLATED_ROOT': str(self.root),
                'DJANGO_SECRET_KEY': secrets.token_urlsafe(48),
                'AI_CONFIG_ENCRYPTION_KEY': base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
                'DIRECT_DEBUG_TOKEN': secrets.token_urlsafe(48),
                'DIRECT_DEBUG_DEVICE_ID': '1', 'DIRECT_DEBUG_API_PORT': str(self.api_port),
                'DIRECT_DEBUG_H5_ORIGIN': self.h5_origin,
            }
            python = str(ROOT / 'backend/.venv/bin/python')
            migrate = self._spawn([python, 'backend/manage.py', 'migrate', '--noinput'], 'migrate', self.env)
            if migrate.wait(timeout=90) != 0:
                raise RuntimeError('Isolated database migration failed.')
            api_socket.close()
            api = self._spawn([python, '-u', 'backend/manage.py', 'runserver',
                               f'127.0.0.1:{self.api_port}', '--noreload'], 'api', self.env)
            self._ready(self.api_origin + '/api/health/', api, b'"ok"')
            node = shutil.which('node')
            if not node:
                raise RuntimeError('Node is required for the isolated storefront.')
            h5_socket.close()
            h5 = self._spawn([node, 'server.mjs'], 'storefront', {
                'PATH': self.env['PATH'], 'PORT': str(self.h5_port), 'HOST': '127.0.0.1',
                'CATALOG_BACKEND_URL': self.api_origin,
            })
            self._ready(self.h5_origin + '/', h5, b'<html')
            self._ready(self.h5_origin + '/api/health/', h5, b'"ok"')
            return self
        except BaseException:
            self.close()
            raise

    def close(self):
        for child in reversed(self.children):
            if child.poll() is None:
                child.terminate()
        for child in reversed(self.children):
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        for stream in self.files:
            stream.close()
        for sock in self.reservations:
            sock.close()
        if self.temp:
            self.temp.cleanup()
        # Do not leave synthetic secrets reachable after shutdown.
        self.env = None

    def __exit__(self, *exc):
        self.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-port', type=int, default=0)
    parser.add_argument('--h5-port', type=int, default=0)
    parser.add_argument('--check', action='store_true', help='Start, check HTTP readiness, then clean up.')
    args = parser.parse_args()

    def stop(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    try:
        with IsolatedRuntime(args.api_port, args.h5_port) as runtime:
            print(json.dumps({'status': 'ready', 'api': runtime.api_origin,
                              'storefront': runtime.h5_origin, 'database': 'new-empty-temporary',
                              'browser_isolation': False}), flush=True)
            if not args.check:
                while True:
                    if any(child.poll() is not None for child in runtime.children[1:]):
                        raise RuntimeError('Isolated service stopped unexpectedly.')
                    time.sleep(0.2)
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
        # Logs may contain request data. Never echo them or environment values.
        print('Isolated runtime failed; temporary services and files cleaned up.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
