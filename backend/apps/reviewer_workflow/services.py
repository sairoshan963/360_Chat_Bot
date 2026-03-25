from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError, NotFound, PermissionDenied

from apps.audit.models import AuditLog
from apps.notifications.models import Notification
from .models import ReviewerTask, PeerNomination


# ─── Tasks ────────────────────────────────────────────────────────────────────

def get_my_tasks(user):
    """
    Returns all tasks where the user is the reviewer,
    for cycles that are ACTIVE, CLOSED, or RESULTS_RELEASED.
    """
    return (
        ReviewerTask.objects
        .filter(
            reviewer=user,
            cycle__state__in=['ACTIVE', 'CLOSED', 'RESULTS_RELEASED']
        )
        .select_related('cycle__template', 'reviewee')
        .prefetch_related('cycle__template__sections__questions')
        .order_by('cycle__review_deadline')
    )


def get_task(task_id, user):
    try:
        task = ReviewerTask.objects.select_related(
            'cycle__template', 'reviewee', 'reviewer'
        ).prefetch_related(
            'cycle__template__sections__questions',
            'response__answers__question',
        ).get(id=task_id)
    except ReviewerTask.DoesNotExist:
        raise NotFound('Task not found')

    if task.reviewer != user:
        raise PermissionDenied('Access denied')

    return task


def save_draft(task_id, user, answers):
    from apps.review_cycles.models import TemplateQuestion

    task = get_task(task_id, user)

    if task.status not in ['CREATED', 'PENDING', 'IN_PROGRESS']:
        raise ValidationError('Task is already submitted or locked')

    if task.cycle.state != 'ACTIVE':
        raise ValidationError('Cycle is not in active state')

    # Validate that all question IDs in the draft belong to this cycle's template
    if answers:
        valid_q_ids = set(
            str(qid) for qid in
            TemplateQuestion.objects.filter(
                section__template=task.cycle.template
            ).values_list('id', flat=True)
        )
        submitted_q_ids = {str(a['question_id']) for a in answers if 'question_id' in a}
        unknown = submitted_q_ids - valid_q_ids
        if unknown:
            raise ValidationError('Draft contains invalid question IDs')

    task.status        = 'IN_PROGRESS'
    task.draft_answers = answers
    task.save(update_fields=['status', 'draft_answers', 'updated_at'])
    return task


# ─── Nominations ──────────────────────────────────────────────────────────────

def get_my_nominations(cycle_id, user):
    """Employee: see their own nominations for a cycle."""
    return PeerNomination.objects.filter(
        cycle_id=cycle_id, reviewee=user
    ).select_related('peer')


def submit_nominations(cycle_id, user, peer_ids):
    """
    Employee submits their peer nominations.
    Replaces existing nominations (delete + recreate).
    If cycle.nomination_approval_mode == AUTO → status=APPROVED immediately.
    """
    from apps.review_cycles.models import ReviewCycle, CycleParticipant

    try:
        cycle = ReviewCycle.objects.get(id=cycle_id)
    except ReviewCycle.DoesNotExist:
        raise NotFound('Cycle not found')

    if cycle.state != 'NOMINATION':
        raise ValidationError('Nominations can only be submitted when cycle is in NOMINATION state')

    if not CycleParticipant.objects.filter(cycle=cycle, user=user).exists():
        raise PermissionDenied('You are not a participant in this cycle')

    # Deduplicate peer_ids while preserving intent — duplicates are a client bug
    peer_ids = list(dict.fromkeys(str(p) for p in peer_ids))

    # Cannot nominate yourself
    if str(user.id) in peer_ids:
        raise ValidationError('You cannot nominate yourself')

    # All nominated peers must be participants in this cycle
    participant_ids = set(
        str(uid) for uid in
        CycleParticipant.objects.filter(cycle=cycle).values_list('user_id', flat=True)
    )
    invalid_peers = [pid for pid in peer_ids if pid not in participant_ids]
    if invalid_peers:
        raise ValidationError(
            f'{len(invalid_peers)} nominated peer(s) are not participants in this cycle'
        )

    if cycle.peer_max_count and len(peer_ids) > cycle.peer_max_count:
        raise ValidationError(f'You can nominate at most {cycle.peer_max_count} peers')

    if cycle.peer_min_count and len(peer_ids) < cycle.peer_min_count:
        raise ValidationError(f'You must nominate at least {cycle.peer_min_count} peers')

    auto_approve = cycle.nomination_approval_mode == 'AUTO'
    new_status   = 'APPROVED' if auto_approve else 'PENDING'

    with transaction.atomic():
        # Keep APPROVED nominations — only delete PENDING/REJECTED so manager approvals
        # are not wiped when an employee re-submits to replace a rejected nomination.
        already_approved_ids = set(
            str(pid) for pid in
            PeerNomination.objects.filter(
                cycle=cycle, reviewee=user, status='APPROVED'
            ).values_list('peer_id', flat=True)
        )

        # Remove only non-approved nominations so they can be replaced
        PeerNomination.objects.filter(
            cycle=cycle, reviewee=user, status__in=['PENDING', 'REJECTED']
        ).delete()

        # Only create new nominations for peers not already approved
        new_peer_ids = [pid for pid in peer_ids if pid not in already_approved_ids]
        nominations = [
            PeerNomination(
                cycle=cycle,
                reviewee=user,
                peer_id=peer_id,
                nominated_by=user,
                status=new_status,
            )
            for peer_id in new_peer_ids
        ]
        if nominations:
            PeerNomination.objects.bulk_create(nominations, ignore_conflicts=True)

    AuditLog.log(actor=user, action='SUBMIT_NOMINATIONS',
                 entity_type='cycle', entity_id=cycle_id,
                 new_value={
                     'nominated_by': user.get_full_name(),
                     'cycle': cycle.name,
                     'peer_count': len(peer_ids),
                     'status': status,
                 })

    return PeerNomination.objects.filter(cycle=cycle, reviewee=user).select_related('peer')


def get_all_nominations(cycle_id):
    """HR/Manager: see all nominations for a cycle."""
    return PeerNomination.objects.filter(
        cycle_id=cycle_id
    ).select_related('reviewee', 'peer').order_by('reviewee__last_name', 'peer__last_name')


def get_pending_approvals_for_manager(cycle_id, manager):
    """
    Manager sees only nominations of their direct reports that are PENDING.
    """
    direct_report_ids = manager.direct_reports.values_list('employee_id', flat=True)
    return PeerNomination.objects.filter(
        cycle_id=cycle_id,
        reviewee_id__in=direct_report_ids,
        status='PENDING',
    ).select_related('reviewee', 'peer')


def decide_nomination(nomination_id, status, actor, rejection_note=None):
    """
    HR or Manager approves/rejects a nomination.
    Manager can only decide on their direct reports.
    """
    try:
        nomination = PeerNomination.objects.select_related(
            'reviewee__manager_relation__manager'
        ).get(id=nomination_id)
    except PeerNomination.DoesNotExist:
        raise NotFound('Nomination not found')

    if status not in ['APPROVED', 'REJECTED']:
        raise ValidationError('Status must be APPROVED or REJECTED')

    if rejection_note and len(rejection_note) > 2000:
        raise ValidationError('Rejection note cannot exceed 2000 characters')

    # Manager scope check — use explicit DB query to avoid try/except swallowing PermissionDenied
    if actor.role == 'MANAGER':
        from apps.users.models import OrgHierarchy
        if not OrgHierarchy.objects.filter(employee=nomination.reviewee, manager=actor).exists():
            raise PermissionDenied('You can only decide on nominations for your direct reports')

    nomination.status         = status
    nomination.approved_by    = actor if status == 'APPROVED' else None
    nomination.approved_at    = timezone.now() if status == 'APPROVED' else None
    nomination.rejection_note = rejection_note if status == 'REJECTED' else None
    nomination.save(update_fields=['status', 'approved_by', 'approved_at', 'rejection_note'])

    AuditLog.log(actor=actor, action=f'NOMINATION_{status}',
                 entity_type='peer_nomination', entity_id=nomination_id,
                 new_value={
                     'decided_by': actor.get_full_name(),
                     'reviewee': nomination.reviewee.get_full_name(),
                     'peer': nomination.peer.get_full_name(),
                     'status': status,
                     **(({'rejection_note': rejection_note}) if rejection_note else {}),
                 })

    # Notify reviewee if rejected
    if status == 'REJECTED':
        Notification.objects.create(
            user=nomination.reviewee,
            type='GENERAL',
            title='Nomination Rejected',
            message=f'One of your peer nominations was rejected. '
                    f'{("Reason: " + rejection_note) if rejection_note else "Please submit a replacement."}',
            link='/employee/nominations',
        )

    return nomination
