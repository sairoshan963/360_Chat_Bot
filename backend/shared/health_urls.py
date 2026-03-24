import logging

from django.urls import path
from django.http import JsonResponse
from django.db import connection

logger = logging.getLogger(__name__)


def health(request):
    return JsonResponse({'success': True, 'status': 'ok'})


def health_db(request):
    try:
        connection.ensure_connection()
        return JsonResponse({'success': True, 'db': 'ok'})
    except Exception as e:
        # Log internally but never expose DB error details externally
        logger.error('Health DB check failed: %s', e, exc_info=True)
        return JsonResponse({'success': False, 'db': 'error'}, status=503)


urlpatterns = [
    path('',    health,    name='health'),
    path('db/', health_db, name='health-db'),
]
