import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')

app = Celery('config')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# ─── Scheduled Jobs ───────────────────────────────────────────────────────────

app.conf.beat_schedule = {
    # Auto-close ACTIVE cycles past their review_deadline (every 30 min)
    'auto-close-cycles': {
        'task': 'apps.review_cycles.tasks.auto_close_cycles',
        'schedule': crontab(minute='*/30'),
    },
    # Send reminder emails to reviewers with pending tasks (every hour)
    'send-reminders': {
        'task': 'apps.review_cycles.tasks.send_reminders',
        'schedule': crontab(minute=0),
    },
}
