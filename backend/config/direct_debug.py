"""Separate local database and transport; never used by deployed settings."""
import os
from django.core.exceptions import ImproperlyConfigured

_isolated = os.environ.get('DIRECT_DEBUG_ISOLATED', '0')
if _isolated not in ('0', '1'):
    raise ImproperlyConfigured('DIRECT_DEBUG_ISOLATED must be 0 or 1.')
if _isolated == '1':
    from .direct_debug_isolation import isolated_options, block_outbound_network
    # Fail before settings can read/create local secrets or select the user's DB.
    _options = isolated_options(os.environ)

from .settings import *  # noqa: F403

if not DEBUG:
    raise ImproperlyConfigured('Direct debug requires local DEBUG mode.')
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3',
                       'NAME': BASE_DIR / '.direct-debug.sqlite3'}}
DIRECT_DEBUG_ENABLED = True
DIRECT_DEBUG_DEVICE_ID = int(os.environ.get('DIRECT_DEBUG_DEVICE_ID', '0'))
DIRECT_DEBUG_TOKEN = (os.environ['DIRECT_DEBUG_TOKEN'] if _isolated == '1'
                      else (BASE_DIR / '.local-direct-debug-token').read_text().strip())
DIRECT_DEBUG_H5_ORIGIN = os.environ.get('DIRECT_DEBUG_H5_ORIGIN', 'http://127.0.0.1:4174')
SUPPLIER_ORDER_ENABLED = False
SUPPLIER_PAYMENT_ENABLED = False
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

if _isolated == '1':
    globals().update(_options)
    block_outbound_network()
