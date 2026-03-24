"""
Celery background tasks — mirrors the Node.js scheduler.js logic exactly.

auto_close_cycles  — runs every 30 min
send_reminders     — runs every hour (smart escalation)
"""
from celery import shared_task
from django.db import transaction
from django.utils import timezone

import logging
logger = logging.getLogger(__name__)


@shared_task
def auto_close_cycles():
    """
    Find all ACTIVE cycles past their review_deadline.
    For each: lock all tasks → aggregate results → close cycle → notify participants.
    Uses select_for_update to prevent race conditions.
    """
    from .models import ReviewCycle, CycleParticipant
    from apps.reviewer_workflow.models import ReviewerTask
    from apps.notifications.models import Notification
    from apps.audit.models import AuditLog
    from apps.feedback.services import aggregate_cycle

    now     = timezone.now()
    expired = ReviewCycle.objects.filter(state='ACTIVE', review_deadline__lt=now)

    for cycle in expired:
        try:
            with transaction.atomic():
                # Re-fetch with row lock — prevent race condition
                locked_cycle = ReviewCycle.objects.select_for_update().get(id=cycle.id)
                if locked_cycle.state != 'ACTIVE':
                    continue

                # Lock all tasks (include CREATED — never-started tasks)
                ReviewerTask.objects.filter(
                    cycle=locked_cycle, status__in=['CREATED', 'PENDING', 'IN_PROGRESS']
                ).update(status='LOCKED')

                # Aggregate (idempotent — safe to re-run)
                aggregate_cycle(locked_cycle)

                locked_cycle.state = 'CLOSED'
                locked_cycle.save(update_fields=['state', 'updated_at'])

            # Audit log (outside transaction — non-critical)
            AuditLog.log(
                actor=None, action='CLOSE_CYCLE',
                entity_type='review_cycle', entity_id=cycle.id,
                new_value={'state': 'CLOSED', 'triggered_by': 'scheduler', 'deadline': str(cycle.review_deadline)},
            )

            # Notify participants
            participant_ids = CycleParticipant.objects.filter(cycle=cycle).values_list('user_id', flat=True)
            Notification.objects.bulk_create([
                Notification(
                    user_id=uid,
                    type='CYCLE_CLOSED',
                    title='Review Cycle Closed',
                    message=f'The review cycle "{cycle.name}" has been closed. Results will be released soon.',
                    link='/employee/report',
                )
                for uid in participant_ids
            ], ignore_conflicts=True)

            logger.info(f'[AUTO-CLOSE] Cycle closed: {cycle.name} ({cycle.id})')

        except Exception as e:
            logger.error(f'[AUTO-CLOSE ERROR] Cycle {cycle.id}: {e}')


@shared_task
def send_reminders():
    """
    Smart reminder escalation (mirrors scheduler.js logic):

    Day 1–2 after activation  → no reminder
    Day 3 to N-3              → daily at 9am IST
    Last 3 days               → daily at 9am IST
    Final day                 → 8am + 2pm IST
    Already submitted         → excluded
    """
    import math
    from django.conf import settings
    from .models import ReviewCycle
    from apps.reviewer_workflow.models import ReviewerTask
    from apps.notifications.models import Notification
    from shared.email import send_reminder

    now = timezone.now()
    tz  = settings.TIME_ZONE

    def local_hour(dt):
        import zoneinfo
        try:
            local_dt = dt.astimezone(zoneinfo.ZoneInfo(tz))
            return local_dt.hour
        except Exception:
            return dt.hour

    local_h = local_hour(now)

    # All active cycles with pending tasks and future deadline
    pending_tasks = (
        ReviewerTask.objects
        .filter(cycle__state='ACTIVE', status__in=['PENDING', 'IN_PROGRESS'], cycle__review_deadline__gt=now)
        .select_related('reviewer', 'cycle')
        .values('reviewer_id', 'reviewer__email', 'reviewer__first_name', 'cycle_id',
                'cycle__name', 'cycle__review_deadline')
        .distinct()
    )

    # Group by reviewer + cycle
    grouped = {}
    for t in pending_tasks:
        key = (str(t['reviewer_id']), str(t['cycle_id']))
        if key not in grouped:
            grouped[key] = {
                'reviewer_id':    t['reviewer_id'],
                'email':          t['reviewer__email'],
                'first_name':     t['reviewer__first_name'],
                'cycle_id':       t['cycle_id'],
                'cycle_name':     t['cycle__name'],
                'review_deadline': t['cycle__review_deadline'],
                'count':          0,
            }
        grouped[key]['count'] += 1

    reminder_count = 0

    for group in grouped.values():
        deadline       = group['review_deadline']
        days_until     = math.ceil((deadline - now).total_seconds() / 86400)

        # Estimate activation time: earliest task creation for this cycle
        earliest_task  = ReviewerTask.objects.filter(cycle_id=group['cycle_id']).order_by('created_at').first()
        activated_at   = earliest_task.created_at if earliest_task else now
        days_since     = math.floor((now - activated_at).total_seconds() / 86400)

        if days_since < 2:
            continue

        should_remind = False
        if days_until <= 1:
            should_remind = local_h in (8, 14)
        elif days_until <= 3 or days_since >= 2:
            should_remind = (local_h == 9)

        if not should_remind:
            continue

        # ── Deduplication: skip if already sent within this hour window ────────
        try:
            from django.core.cache import cache
            dedup_key = f"reminder:{group['reviewer_id']}:{group['cycle_id']}:{now.strftime('%Y%m%d%H')}"
            if cache.get(dedup_key):
                continue
            cache.set(dedup_key, 1, timeout=3600)  # expire after 1 hour
        except Exception as dedup_err:
            logger.warning('[REMINDER] Dedup cache error (continuing): %s', dedup_err)

        deadline_str = deadline.strftime('%d %B %Y')
        sent = send_reminder(group['email'], group['first_name'], group['cycle_name'], deadline_str)

        if sent:
            logger.info(f"[REMINDER] Sent to {group['email']} | Cycle: {group['cycle_name']} ({group['count']} task(s))")
        else:
            logger.warning(f"[REMINDER] Failed/skipped for {group['email']}")

        # In-app notification
        try:
            Notification.objects.create(
                user_id=group['reviewer_id'],
                type='REMINDER',
                title='Feedback Reminder',
                message=f'You have {group["count"]} pending review task(s) in "{group["cycle_name"]}". Deadline: {deadline_str}.',
                link='/employee/tasks',
            )
        except Exception as e:
            logger.error(f'[REMINDER] Notification failed for {group["email"]}: {e}')

        reminder_count += 1

    if reminder_count:
        logger.info(f'[REMINDER ENGINE] {reminder_count} reminder(s) sent (tz: {tz})')
