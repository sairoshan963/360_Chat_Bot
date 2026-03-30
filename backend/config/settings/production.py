from .base import *

DEBUG = False

# Trust X-Forwarded-Proto from Nginx (set by Cloudflare Tunnel / reverse proxy)
SECURE_PROXY_SSL_HEADER    = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST       = True

# SSL redirect handled by Cloudflare — Django must NOT redirect internally
SECURE_SSL_REDIRECT           = False
SESSION_COOKIE_SECURE         = True
CSRF_COOKIE_SECURE            = True
SECURE_BROWSER_XSS_FILTER     = True
SECURE_CONTENT_TYPE_NOSNIFF   = True
X_FRAME_OPTIONS               = 'DENY'
SECURE_HSTS_SECONDS           = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True

# Reduce chat assistant logging in production
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
            'datefmt': '%H:%M:%S',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
        },
    },
    'loggers': {
        # Reduce chat assistant logging to INFO in production
        'apps.chat_assistant': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        # Django internals - WARNING only
        'django': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        # Everything else - INFO
        '': {
            'handlers': ['console'],
            'level': 'INFO',
        },
    },
}
