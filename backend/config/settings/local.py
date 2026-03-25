from .base import *

DEBUG = True

ALLOWED_HOSTS = ['*']

# ─── SQLite for local dev (no PostgreSQL setup needed) ────────────────────────
# Switch to PostgreSQL by setting USE_POSTGRES=true in .env
import os
if os.environ.get('USE_POSTGRES', '').lower() != 'true':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# ─── Email: print to console instead of sending ───────────────────────────────
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Use default (PBKDF2) — MD5 is broken even for dev, no speed benefit worth the risk
