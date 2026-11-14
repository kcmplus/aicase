"""Separate local database and transport; never used by deployed settings."""
from .settings import *  # noqa: F403

if not DEBUG:
    raise ImproperlyConfigured('Direct debug requires local DEBUG mode.')
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3',
                       'NAME': BASE_DIR / '.direct-debug.sqlite3'}}
DIRECT_DEBUG_ENABLED = True
DIRECT_DEBUG_DEVICE_ID = int(os.environ.get('DIRECT_DEBUG_DEVICE_ID', '0'))
DIRECT_DEBUG_TOKEN = (BASE_DIR / '.local-direct-debug-token').read_text().strip()
DIRECT_DEBUG_H5_ORIGIN = os.environ.get('DIRECT_DEBUG_H5_ORIGIN', 'http://127.0.0.1:4174')
SUPPLIER_ORDER_ENABLED = False
SUPPLIER_PAYMENT_ENABLED = False
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
