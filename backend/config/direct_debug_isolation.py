"""Opt-in settings for disposable browser runs, validated before base settings load."""
import base64
import os
from pathlib import Path
import socket
import tempfile
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured


def isolated_options(env):
    def require(name):
        value = env.get(name, '')
        if not value:
            raise ImproperlyConfigured(f'Isolated direct debug requires {name}.')
        return value

    if env.get('DJANGO_DEBUG') != '1':
        raise ImproperlyConfigured('Isolated direct debug requires explicit DJANGO_DEBUG=1.')
    if env.get('POSTGRES_DB'):
        raise ImproperlyConfigured('Isolated direct debug does not accept PostgreSQL settings.')
    root = Path(require('DIRECT_DEBUG_ISOLATED_ROOT'))
    temp = Path(tempfile.gettempdir()).resolve()
    if (not root.is_absolute() or not root.is_dir() or root.is_symlink()
            or root.resolve().parent != temp or not root.name.startswith('aicase-v35-')):
        raise ImproperlyConfigured('Isolated root must be an aicase-v35-* temporary directory.')
    root = root.resolve()
    # All files in this disposable tree must remain in it, including SQLite sidecars.
    for child in root.rglob('*'):
        if child.is_symlink() or (child.is_file() and child.stat().st_nlink != 1):
            raise ImproperlyConfigured('Isolated runtime cannot contain linked files.')
    for name in ('DJANGO_SECRET_KEY', 'AI_CONFIG_ENCRYPTION_KEY', 'DIRECT_DEBUG_TOKEN'):
        if len(require(name)) < 32:
            raise ImproperlyConfigured(f'Isolated direct debug requires a generated {name}.')
    try:
        if len(base64.urlsafe_b64decode(env['AI_CONFIG_ENCRYPTION_KEY'])) != 32:
            raise ValueError()
    except (ValueError, TypeError):
        raise ImproperlyConfigured('Invalid isolated encryption key.') from None
    try:
        device = int(require('DIRECT_DEBUG_DEVICE_ID'))
        port = int(require('DIRECT_DEBUG_API_PORT'))
        origin = urlsplit(require('DIRECT_DEBUG_H5_ORIGIN'))
        h5_port = origin.port
        if (device <= 0 or not 1024 <= port <= 65535
                or origin.scheme != 'http' or origin.hostname != '127.0.0.1'
                or not h5_port or not 1024 <= h5_port <= 65535
                or origin.username or origin.password or origin.path or origin.query or origin.fragment
                or port == h5_port or port in (8000, 8001) or h5_port in (4173, 4174, 5173)):
            raise ValueError()
    except ValueError:
        raise ImproperlyConfigured('Isolated runtime requires a positive device and distinct dedicated loopback ports.') from None
    return {
        'DATABASES': {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': root / 'db.sqlite3'}},
        'MEDIA_ROOT': root / 'media', 'STATIC_ROOT': root / 'static',
        'DIRECT_DEBUG_TOKEN': env['DIRECT_DEBUG_TOKEN'],
        'DIRECT_DEBUG_DEVICE_ID': device, 'DIRECT_DEBUG_API_PORT': port,
        'DIRECT_DEBUG_H5_ORIGIN': env['DIRECT_DEBUG_H5_ORIGIN'],
        'ALLOWED_HOSTS': ['127.0.0.1', 'localhost', 'testserver'],
        'CSRF_TRUSTED_ORIGINS': [env['DIRECT_DEBUG_H5_ORIGIN']],
    }


def block_outbound_network():
    """Process-local guard; incoming browser requests still work. No subprocess sandbox claim."""
    def denied(*args, **kwargs):
        raise OSError('Outbound network is disabled in isolated direct debug.')

    resolve = socket.getaddrinfo

    def local_resolution(host, *args, **kwargs):
        if host not in (None, 'localhost', '127.0.0.1', '::1'):
            return denied()
        return resolve(host, *args, **kwargs)

    socket.socket.connect = denied
    socket.socket.connect_ex = denied
    socket.socket.sendto = denied
    # UDP sendmsg can supply a destination without ever calling connect/sendto.
    # It is not available on every platform; keep the guard portable.
    if hasattr(socket.socket, 'sendmsg'):
        socket.socket.sendmsg = denied
    socket.create_connection = denied
    socket.getaddrinfo = local_resolution
    socket.gethostbyname = denied
    socket.gethostbyname_ex = denied
    socket.gethostbyaddr = denied
