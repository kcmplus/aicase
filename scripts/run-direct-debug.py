"""Run a supplier-free API using an isolated, persistent copy of local data."""
import argparse
import os
from pathlib import Path
import secrets
import sqlite3
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--device-id', default='789')
parser.add_argument('--shop-id', default='351')
parser.add_argument('--port', type=int, default=8001)
parser.add_argument('--h5-origin', default='http://127.0.0.1:4174')
parser.add_argument('--check', action='store_true', help='Prepare the isolated database without starting a server.')
args = parser.parse_args()
origin = urlsplit(args.h5_origin)
if origin.scheme not in ('http', 'https') or not origin.hostname or origin.username or origin.password or origin.query or origin.fragment or origin.path not in ('', '/'):
    parser.error('--h5-origin must be an HTTP(S) origin.')
source, target = ROOT / 'backend/db.sqlite3', ROOT / 'backend/.direct-debug.sqlite3'
if not target.exists():
    if not source.is_file():
        parser.error('Local backend/db.sqlite3 with device catalog is required.')
    with sqlite3.connect(f'file:{source}?mode=ro', uri=True) as src, sqlite3.connect(target) as dest:
        src.backup(dest)
    target.chmod(0o600)
token = ROOT / 'backend/.local-direct-debug-token'
try:
    fd = os.open(token, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as out:
        out.write(secrets.token_urlsafe(48))
except FileExistsError:
    pass
os.environ.update(DJANGO_SETTINGS_MODULE='config.direct_debug', DJANGO_DEBUG='1',
                  DIRECT_DEBUG_H5_ORIGIN=args.h5_origin.rstrip('/'))
sys.path.insert(0, str(ROOT / 'backend'))
import django
django.setup()
from django.core.management import call_command
from management_api.models import Device, PricingPlan
call_command('migrate', interactive=False, verbosity=0)
matches = list(Device.objects.filter(vendor_device_id=args.device_id, connection__shop_id=args.shop_id,
                                    active=True, connection__active=True)[:2])
if len(matches) != 1:
    parser.error('Device/shop must identify exactly one active device in the local copy.')
from django.conf import settings
settings.DIRECT_DEBUG_DEVICE_ID = matches[0].pk
os.environ['DIRECT_DEBUG_DEVICE_ID'] = str(matches[0].pk)
from management_api.store_catalog import available_stocks
if not available_stocks().exists():
    parser.error('This device has no usable templates/stock in the local copy.')
plan = PricingPlan.objects.filter(kind='print', active=True).first()
if not plan:
    parser.error('The local copy requires an active print pricing plan.')
plan.price = 0
plan.save(update_fields=['price', 'updated_at'])
print(f'直连调试：device_id={args.device_id}, shop_id={args.shop_id}；独立数据库；0 元免付；模拟硬件。', flush=True)
if not args.check:
    os.chdir(ROOT)
    os.execv(sys.executable, [sys.executable, '-u', 'backend/manage.py', 'runserver',
                            f'127.0.0.1:{args.port}', '--noreload'])
