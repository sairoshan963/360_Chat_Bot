from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError, NotFound, PermissionDenied

from apps.audit.models import AuditLog
from apps.notifications.models import Notification
from .models import ReviewCycle, CycleParticipant, Template, TemplateSection, TemplateQuestion


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_cycle_or_404(cycle_id):
    try:
        return ReviewCycle.objects.select_related('template').get(id=cycle_id)
    except ReviewCycle.DoesNotExist:
        raise NotFound('Review cycle not found')


def _notify_participants(cycle, notif_type, title, message, link):
    participant_ids = CycleParticipant.objects.filter(cycle=cycle).values_list('user_id', flat=True)
    notifications = [
        Notification(user_id=uid, type=notif_type, title=title, message=message, link=link)
        for uid in participant_ids
    ]
    Notification.objects.bulk_create(notifications, ignore_conflicts=True)


def _generate_reviewer_tasks(cycle, participants):
    """
    Generate all ReviewerTask records for a cycle.
    SELF + MANAGER + PEER (approved nominations only) tasks are created.
    Called inside an atomic transaction.
    """
    from apps.reviewer_workflow.models import ReviewerTask, PeerNomination

    participant_ids = {str(p.user_id) for p in participants}
    tasks_to_create = []

    for participant in participants:
        user    = participant.user
        user_id = str(user.id)

        # SELF
        tasks_to_create.append(ReviewerTask(
            cycle=cycle, reviewee=user, reviewer=user,
            reviewer_type='SELF', anonymity_mode=cycle.self_anonymity,
        ))

        # MANAGER
        try:
            manager = user.manager_relation.manager
            if str(manager.id) in participant_ids:
                tasks_to_create.append(ReviewerTask(
                    cycle=cycle, reviewee=user, reviewer=manager,
                    reviewer_type='MANAGER', anonymity_mode=cycle.manager_anonymity,
                ))
        except Exception:
            pass

        # PEERS (from approved nominations)
        if cycle.peer_enabled:
            approved_nominations = PeerNomination.objects.filter(
                cycle=cycle, reviewee=user, status='APPROVED'
            ).select_related('peer')
            for nom in approved_nominations:
                if str(nom.peer_id) in participant_ids:
                    tasks_to_create.append(ReviewerTask(
                        cycle=cycle, reviewee=user, reviewer=nom.peer,
                        reviewer_type='PEER', anonymity_mode=cycle.peer_anonymity,
                    ))

    if tasks_to_create:
        ReviewerTask.objects.bulk_create(tasks_to_create, ignore_conflicts=True)


# ─── Templates ────────────────────────────────────────────────────────────────

def list_templates():
    return Template.objects.select_related('created_by').filter(is_active=True)


def get_template(template_id):
    try:
        return Template.objects.prefetch_related('sections__questions').get(id=template_id)
    except Template.DoesNotExist:
        raise NotFound('Template not found')


VALID_QUESTION_TYPES = [t[0] for t in TemplateQuestion.QUESTION_TYPE_CHOICES]


def _validate_question(q):
    """Validate a single question dict. Raises ValidationError on bad data."""
    q_type = q.get('type', 'RATING')
    if q_type not in VALID_QUESTION_TYPES:
        raise ValidationError(f'Invalid question type: {q_type}. Must be one of {VALID_QUESTION_TYPES}')
    if q_type == 'RATING':
        r_min = q.get('rating_scale_min')
        r_max = q.get('rating_scale_max')
        if r_min is None or r_max is None:
            raise ValidationError('rating_scale_min and rating_scale_max are required for RATING questions')
        if not isinstance(r_min, int) or not isinstance(r_max, int):
            raise ValidationError('rating_scale_min and rating_scale_max must be integers')
        if r_min < 1:
            raise ValidationError('rating_scale_min must be ≥ 1')
        if r_max > 10:
            raise ValidationError('rating_scale_max must be ≤ 10')
        if r_min >= r_max:
            raise ValidationError('rating_scale_min must be less than rating_scale_max')


def create_template(name, description, sections, actor):
    if not name:
        raise ValidationError('Template name is required')

    with transaction.atomic():
        template = Template.objects.create(
            name=name,
            description=description or None,
            created_by=actor,
        )
        for i, sec in enumerate(sections or []):
            if not sec.get('title'):
                continue
            section = TemplateSection.objects.create(
                template=template,
                title=sec['title'].strip(),
                display_order=sec.get('display_order', i + 1),
            )
            for j, q in enumerate(sec.get('questions') or []):
                _validate_question(q)
                TemplateQuestion.objects.create(
                    section=section,
                    question_text=q['question_text'].strip(),
                    type=q.get('type', 'RATING'),
                    rating_scale_min=q.get('rating_scale_min'),
                    rating_scale_max=q.get('rating_scale_max'),
                    is_required=q.get('is_required', True),
                    display_order=q.get('display_order', j + 1),
                )

    return Template.objects.prefetch_related('sections__questions').get(id=template.id)


def update_template(template_id, name, sections, actor):
    try:
        template = Template.objects.get(id=template_id)
    except Template.DoesNotExist:
        raise NotFound('Template not found')

    # Cannot edit if used by an active/finalized cycle
    if ReviewCycle.objects.filter(template=template).exclude(state='DRAFT').exists():
        raise ValidationError('Template is used by an active or finalized cycle and cannot be edited')

    with transaction.atomic():
        template.name = name.strip()
        template.save(update_fields=['name', 'updated_at'])

        template.sections.all().delete()
        for i, sec in enumerate(sections or []):
            section = TemplateSection.objects.create(
                template=template,
                title=sec['title'].strip(),
                display_order=i + 1,
            )
            for j, q in enumerate(sec.get('questions') or []):
                _validate_question(q)
                TemplateQuestion.objects.create(
                    section=section,
                    question_text=q['question_text'].strip(),
                    type=q.get('type', 'RATING'),
                    rating_scale_min=q.get('rating_scale_min') if q.get('type') == 'RATING' else None,
                    rating_scale_max=q.get('rating_scale_max') if q.get('type') == 'RATING' else None,
                    is_required=q.get('is_required', True),
                    display_order=j + 1,
                )

    return Template.objects.prefetch_related('sections__questions').get(id=template.id)


# ─── Cycles ───────────────────────────────────────────────────────────────────

def list_cycles(state=None):
    qs = ReviewCycle.objects.select_related('template', 'created_by')
    if state:
        valid = [s[0] for s in ReviewCycle.STATE_CHOICES]
        if state not in valid:
            raise ValidationError('Invalid state filter')
        qs = qs.filter(state=state)
    return qs


def get_cycle(cycle_id):
    return _get_cycle_or_404(cycle_id)


def get_my_cycles(user):
    return ReviewCycle.objects.filter(
        participations__user=user
    ).exclude(state='DRAFT').order_by('-created_at')


def create_cycle(data, actor):
    name             = data.get('name')
    template_id      = data.get('template_id')
    review_deadline  = data.get('review_deadline')

    if not name:           raise ValidationError('name is required')
    if not template_id:    raise ValidationError('template_id is required')
    if not review_deadline: raise ValidationError('review_deadline is required')

    try:
        template = Template.objects.get(id=template_id, is_active=True)
    except Template.DoesNotExist:
        raise NotFound('Template not found or inactive')

    peer_enabled = data.get('peer_enabled', False)
    nomination_deadline = data.get('nomination_deadline')
    if peer_enabled:
        peer_min = data.get('peer_min_count')
        peer_max = data.get('peer_max_count')
        if not peer_min or not peer_max:
            raise ValidationError('peer_min_count and peer_max_count required when peer_enabled')
        if peer_min > peer_max:
            raise ValidationError('peer_min_count must be ≤ peer_max_count')
        if peer_min < 1:
            raise ValidationError('peer_min_count must be ≥ 1')
        if not nomination_deadline:
            raise ValidationError('nomination_deadline is required when peer_enabled')

    if nomination_deadline and nomination_deadline >= review_deadline:
        raise ValidationError('nomination_deadline must be before review_deadline')

    valid_anonymity = [a[0] for a in ReviewCycle.ANONYMITY_CHOICES]
    for field in ['peer_anonymity', 'manager_anonymity', 'self_anonymity']:
        val = data.get(field)
        if val and val not in valid_anonymity:
            raise ValidationError(f'Invalid {field} value')

    cycle = ReviewCycle.objects.create(
        name=name,
        description=data.get('description') or None,
        template=template,
        peer_enabled=peer_enabled,
        peer_min_count=data.get('peer_min_count') or None,
        peer_max_count=data.get('peer_max_count') or None,
        peer_threshold=data.get('peer_threshold') or 3,
        peer_anonymity=data.get('peer_anonymity') or 'ANONYMOUS',
        manager_anonymity=data.get('manager_anonymity') or 'TRANSPARENT',
        self_anonymity=data.get('self_anonymity') or 'TRANSPARENT',
        nomination_deadline=data.get('nomination_deadline') or None,
        review_deadline=review_deadline,
        quarter=data.get('quarter') or None,
        quarter_year=data.get('quarter_year') or None,
        nomination_approval_mode=data.get('nomination_approval_mode') or 'AUTO',
        created_by=actor,
    )

    participant_ids = data.get('participant_ids', [])
    if participant_ids:
        add_participants(cycle.id, participant_ids, actor)

    AuditLog.log(actor=actor, action='CREATE_CYCLE', entity_type='review_cycle', entity_id=cycle.id,
                 new_value={'name': name, 'state': 'DRAFT'})
    return cycle


def update_cycle(cycle_id, data, actor):
    cycle = _get_cycle_or_404(cycle_id)
    if cycle.state != 'DRAFT':
        raise ValidationError('Cycle can only be updated in DRAFT state')

    # ── Peer settings validation ──────────────────────────────────────────────
    peer_enabled = data.get('peer_enabled', cycle.peer_enabled)
    if peer_enabled:
        peer_min = data.get('peer_min_count', cycle.peer_min_count)
        peer_max = data.get('peer_max_count', cycle.peer_max_count)
        if not peer_min or not peer_max:
            raise ValidationError('peer_min_count and peer_max_count are required when peer_enabled')
        if peer_min < 1:
            raise ValidationError('peer_min_count must be ≥ 1')
        if peer_min > peer_max:
            raise ValidationError('peer_min_count must be ≤ peer_max_count')
        nomination_deadline = data.get('nomination_deadline', cycle.nomination_deadline)
        if not nomination_deadline:
            raise ValidationError('nomination_deadline is required when peer_enabled')

    # ── Anonymity choices validation ──────────────────────────────────────────
    valid_anonymity = [a[0] for a in ReviewCycle.ANONYMITY_CHOICES]
    for field in ['peer_anonymity', 'manager_anonymity', 'self_anonymity']:
        val = data.get(field)
        if val and val not in valid_anonymity:
            raise ValidationError(f'Invalid {field} value: {val}')

    # ── Deadline ordering validation ──────────────────────────────────────────
    review_deadline     = data.get('review_deadline', cycle.review_deadline)
    nomination_deadline = data.get('nomination_deadline', cycle.nomination_deadline)
    if nomination_deadline and review_deadline and nomination_deadline >= review_deadline:
        raise ValidationError('nomination_deadline must be before review_deadline')

    allowed = ['name', 'description', 'peer_enabled', 'peer_min_count', 'peer_max_count',
               'peer_threshold', 'peer_anonymity', 'manager_anonymity', 'self_anonymity',
               'nomination_deadline', 'review_deadline', 'quarter', 'quarter_year']
    for field in allowed:
        if field in data:
            setattr(cycle, field, data[field])
    cycle.save()

    AuditLog.log(actor=actor, action='UPDATE_CYCLE', entity_type='review_cycle',
                 entity_id=cycle.id, new_value=data)
    return cycle


def add_participants(cycle_id, user_ids, actor):
    cycle = _get_cycle_or_404(cycle_id)
    if cycle.state not in ['DRAFT', 'NOMINATION']:
        raise ValidationError('Participants can only be added in DRAFT or NOMINATION state')

    from apps.users.models import User
    participants = [
        CycleParticipant(cycle=cycle, user_id=uid)
        for uid in user_ids
    ]
    CycleParticipant.objects.bulk_create(participants, ignore_conflicts=True)
    return CycleParticipant.objects.filter(cycle=cycle).select_related('user')


def get_participants(cycle_id):
    cycle = _get_cycle_or_404(cycle_id)
    return CycleParticipant.objects.filter(cycle=cycle).select_related('user__department', 'user__manager_relation__manager')


# ─── State Machine ────────────────────────────────────────────────────────────

def activate_cycle(cycle_id, actor):
    """DRAFT → NOMINATION or DRAFT → ACTIVE (if peer disabled)"""
    with transaction.atomic():
        cycle = ReviewCycle.objects.select_for_update().get(id=cycle_id)
        if cycle.state != 'DRAFT':
            raise ValidationError(f'Cannot activate from state: {cycle.state}')

        participants = list(
            CycleParticipant.objects.filter(cycle=cycle).select_related('user__manager_relation__manager')
        )
        if not participants:
            raise ValidationError('Add at least one participant before activating')

        next_state = 'NOMINATION' if (cycle.peer_enabled and cycle.nomination_deadline) else 'ACTIVE'
        cycle.state = next_state

        if next_state == 'ACTIVE':
            _generate_reviewer_tasks(cycle, participants)

        cycle.save(update_fields=['state', 'updated_at'])

    AuditLog.log(actor=actor, action='ACTIVATE_CYCLE', entity_type='review_cycle',
                 entity_id=cycle_id, old_value={'state': 'DRAFT'},
                 new_value={'cycle': cycle.name, 'state': next_state})

    if next_state == 'ACTIVE':
        _notify_participants(cycle, 'CYCLE_ACTIVATED', 'Review Cycle Started',
            f'The review cycle "{cycle.name}" is now active. Please complete your assigned feedback tasks.',
            '/employee/tasks')
    else:
        _notify_participants(cycle, 'NOMINATION_OPEN', 'Nomination Window Open',
            f'The nomination window for "{cycle.name}" is now open. Please submit your peer nominations.',
            '/employee/nominations')

    return _get_cycle_or_404(cycle_id)


def finalize_cycle(cycle_id, actor):
    """NOMINATION → ACTIVE (snapshot + task generation)"""
    with transaction.atomic():
        cycle = ReviewCycle.objects.select_for_update().get(id=cycle_id)
        if cycle.state != 'NOMINATION':
            raise ValidationError(f'Cannot finalize from state: {cycle.state}')

        participants = list(
            CycleParticipant.objects.filter(cycle=cycle).select_related('user__manager_relation__manager')
        )

        # Validate nomination completeness
        if cycle.peer_enabled:
            _validate_nominations(cycle, participants)

        _generate_reviewer_tasks(cycle, participants)
        cycle.state = 'ACTIVE'
        cycle.save(update_fields=['state', 'updated_at'])

    AuditLog.log(actor=actor, action='FINALIZE_CYCLE', entity_type='review_cycle',
                 entity_id=cycle_id, old_value={'state': 'NOMINATION'},
                 new_value={'cycle': cycle.name, 'state': 'ACTIVE'})

    _notify_participants(cycle, 'CYCLE_ACTIVATED', 'Review Cycle Started',
        f'The review cycle "{cycle.name}" is now active. Please complete your assigned feedback tasks.',
        '/employee/tasks')

    return _get_cycle_or_404(cycle_id)


def _validate_nominations(cycle, participants):
    from apps.reviewer_workflow.models import PeerNomination

    # Block if any nominations still PENDING approval
    pending_count = PeerNomination.objects.filter(cycle=cycle, status='PENDING').count()
    if pending_count > 0:
        raise ValidationError(
            f'{pending_count} nomination(s) are still pending approval. '
            f'Approve or reject them before finalizing.'
        )

    # Check minimum peer count per participant
    if not cycle.peer_min_count:
        return

    incomplete = []
    for p in participants:
        approved = PeerNomination.objects.filter(
            cycle=cycle, reviewee=p.user, status='APPROVED'
        ).count()
        if approved < cycle.peer_min_count:
            incomplete.append(p.user.email)

    if incomplete:
        raise ValidationError(
            f'{len(incomplete)} participant(s) have not met minimum peer nominations: '
            + ', '.join(incomplete)
        )


def close_cycle(cycle_id, actor):
    """ACTIVE → CLOSED — locks all pending tasks"""
    with transaction.atomic():
        cycle = ReviewCycle.objects.select_for_update().get(id=cycle_id)
        if cycle.state != 'ACTIVE':
            raise ValidationError(f'Cannot close from state: {cycle.state}')

        from apps.reviewer_workflow.models import ReviewerTask
        ReviewerTask.objects.filter(
            cycle=cycle, status__in=['CREATED', 'PENDING', 'IN_PROGRESS']
        ).update(status='LOCKED')

        cycle.state = 'CLOSED'
        cycle.save(update_fields=['state', 'updated_at'])

    AuditLog.log(actor=actor, action='CLOSE_CYCLE', entity_type='review_cycle',
                 entity_id=cycle_id, old_value={'state': 'ACTIVE'},
                 new_value={'cycle': cycle.name, 'state': 'CLOSED'})

    return _get_cycle_or_404(cycle_id)


def release_results(cycle_id, actor):
    """CLOSED → RESULTS_RELEASED — runs aggregation pipeline"""
    with transaction.atomic():
        cycle = ReviewCycle.objects.select_for_update().get(id=cycle_id)
        if cycle.state != 'CLOSED':
            raise ValidationError(f'Cannot release results from state: {cycle.state}')

        from apps.reviewer_workflow.models import ReviewerTask
        submitted_count = ReviewerTask.objects.filter(cycle=cycle, status='SUBMITTED').count()
        if submitted_count == 0:
            raise ValidationError(
                'No submitted feedback found for this cycle. '
                'Release results only after at least one feedback is submitted.'
            )

        # Run aggregation
        from apps.feedback.services import aggregate_cycle
        aggregate_cycle(cycle)

        cycle.state = 'RESULTS_RELEASED'
        cycle.results_released_at = timezone.now()
        cycle.save(update_fields=['state', 'results_released_at', 'updated_at'])

    AuditLog.log(actor=actor, action='RELEASE_RESULTS', entity_type='review_cycle',
                 entity_id=cycle_id, old_value={'state': 'CLOSED'},
                 new_value={'cycle': cycle.name, 'state': 'RESULTS_RELEASED'})

    _notify_participants(cycle, 'RESULTS_RELEASED', 'Your Feedback Results Are Ready',
        f'Results for "{cycle.name}" have been released. View your 360° feedback report now.',
        '/employee/report')

    return _get_cycle_or_404(cycle_id)


def archive_cycle(cycle_id, actor):
    """RESULTS_RELEASED → ARCHIVED"""
    with transaction.atomic():
        cycle = ReviewCycle.objects.select_for_update().get(id=cycle_id)
        if cycle.state != 'RESULTS_RELEASED':
            raise ValidationError(f'Cannot archive from state: {cycle.state}')
        cycle.state = 'ARCHIVED'
        cycle.save(update_fields=['state', 'updated_at'])

    AuditLog.log(actor=actor, action='ARCHIVE_CYCLE', entity_type='review_cycle',
                 entity_id=cycle_id, old_value={'state': 'RESULTS_RELEASED'},
                 new_value={'cycle': cycle.name, 'state': 'ARCHIVED'})

    return _get_cycle_or_404(cycle_id)


def override_cycle(cycle_id, target_state, reason, actor):
    """Super Admin emergency override — any state → any state"""
    if not reason or not reason.strip():
        raise ValidationError('reason is required for override actions')

    valid_states = [s[0] for s in ReviewCycle.STATE_CHOICES]
    if target_state not in valid_states:
        raise ValidationError('Invalid target_state')

    with transaction.atomic():
        cycle = ReviewCycle.objects.select_for_update().get(id=cycle_id)
        old_state = cycle.state

        # Lock tasks when moving to a closed state
        if target_state in ['CLOSED', 'RESULTS_RELEASED', 'ARCHIVED']:
            from apps.reviewer_workflow.models import ReviewerTask
            ReviewerTask.objects.filter(
                cycle=cycle, status__in=['CREATED', 'PENDING', 'IN_PROGRESS']
            ).update(status='LOCKED')

        cycle.state = target_state
        cycle.save(update_fields=['state', 'updated_at'])

    AuditLog.log(actor=actor, action='OVERRIDE_ACTION', entity_type='review_cycle',
                 entity_id=cycle_id, old_value={'state': old_state},
                 new_value={'cycle': cycle.name, 'from': old_state, 'to': target_state, 'reason': reason})

    return _get_cycle_or_404(cycle_id)


# ─── Progress & Status ────────────────────────────────────────────────────────

def get_cycle_progress(cycle_id):
    _get_cycle_or_404(cycle_id)
    from apps.reviewer_workflow.models import ReviewerTask
    from django.db.models import Count, Q

    return ReviewerTask.objects.filter(cycle_id=cycle_id).values('reviewer_type').annotate(
        total=Count('id'),
        submitted=Count('id', filter=Q(status='SUBMITTED')),
        locked=Count('id', filter=Q(status='LOCKED')),
        pending=Count('id', filter=Q(status__in=['CREATED', 'PENDING', 'IN_PROGRESS'])),
    )


def get_nomination_status(cycle_id):
    cycle = _get_cycle_or_404(cycle_id)
    from apps.reviewer_workflow.models import PeerNomination
    from django.db.models import Count, Q

    participants = CycleParticipant.objects.filter(cycle=cycle).select_related('user')
    result = []

    for p in participants:
        agg = PeerNomination.objects.filter(cycle=cycle, reviewee=p.user).aggregate(
            nominated=Count('id'),
            approved=Count('id', filter=Q(status='APPROVED')),
            pending=Count('id', filter=Q(status='PENDING')),
            rejected=Count('id', filter=Q(status='REJECTED')),
        )
        nominated = agg['nominated']
        min_req   = cycle.peer_min_count or 0
        status    = 'NOT_STARTED' if nominated == 0 else ('DONE' if nominated >= min_req else 'INCOMPLETE')
        result.append({
            'user_id':    str(p.user.id),
            'email':      p.user.email,
            'first_name': p.user.first_name,
            'last_name':  p.user.last_name,
            'department': p.user.department.name if p.user.department_id else None,
            'min_required': min_req,
            'status':     status,
            **agg,
        })
    return result


def get_participant_task_status(cycle_id):
    _get_cycle_or_404(cycle_id)
    from apps.reviewer_workflow.models import ReviewerTask
    from django.db.models import Count, Q

    participants = CycleParticipant.objects.filter(
        cycle_id=cycle_id
    ).select_related('user__department').prefetch_related(
        'user__tasks_as_reviewer'
    )

    result = []
    for p in participants:
        tasks = ReviewerTask.objects.filter(cycle_id=cycle_id, reviewer=p.user)
        total     = tasks.count()
        submitted = tasks.filter(status='SUBMITTED').count()
        locked    = tasks.filter(status='LOCKED').count()
        pending   = tasks.filter(status__in=['CREATED', 'PENDING', 'IN_PROGRESS']).count()

        if total == 0:           overall = 'NO_TASKS'
        elif pending > 0:        overall = 'PENDING'
        elif submitted == total: overall = 'COMPLETED'
        elif locked == total:    overall = 'MISSED'
        elif submitted > 0:      overall = 'PARTIAL'
        else:                    overall = 'MISSED'

        result.append({
            'user_id':    str(p.user.id),
            'first_name': p.user.first_name,
            'last_name':  p.user.last_name,
            'email':      p.user.email,
            'department': p.user.department.name if p.user.department_id else None,
            'total': total, 'submitted': submitted,
            'locked': locked, 'pending': pending,
            'overall': overall,
        })
    return result
