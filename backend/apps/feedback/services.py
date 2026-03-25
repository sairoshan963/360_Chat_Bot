from django.db import transaction
from django.db.models import Avg
from rest_framework.exceptions import ValidationError, NotFound, PermissionDenied

from apps.audit.models import AuditLog
from apps.reviewer_workflow.models import ReviewerTask
from apps.review_cycles.models import ReviewCycle, CycleParticipant, TemplateQuestion
from .models import FeedbackResponse, FeedbackAnswer, AggregatedResult


# ─── Submit Feedback ──────────────────────────────────────────────────────────

def submit_feedback(task_id, user, answers):
    try:
        task = ReviewerTask.objects.select_related(
            'cycle__template', 'reviewee'
        ).get(id=task_id)
    except ReviewerTask.DoesNotExist:
        raise NotFound('Task not found')

    if task.reviewer != user:
        raise PermissionDenied('Access denied')

    if task.status not in ['CREATED', 'PENDING', 'IN_PROGRESS']:
        raise ValidationError('Task is already submitted or locked')

    if task.cycle.state != 'ACTIVE':
        raise ValidationError('Cycle is not in active state')

    if not answers:
        raise ValidationError('answers array is required')

    # Validate required questions are answered
    required_q_ids = set(
        str(q.id) for q in TemplateQuestion.objects.filter(
            section__template=task.cycle.template, is_required=True
        )
    )
    answered_q_ids = {str(a['question_id']) for a in answers}
    missing = required_q_ids - answered_q_ids
    if missing:
        raise ValidationError(f'Missing required answers for {len(missing)} question(s)')

    # Pre-validate rating values before bulk_create
    questions_map = {
        str(q.id): q for q in TemplateQuestion.objects.filter(
            section__template=task.cycle.template
        )
    }
    
    for answer in answers:
        question_id = str(answer['question_id'])
        rating_value = answer.get('rating_value')
        
        if rating_value is not None and question_id in questions_map:
            question = questions_map[question_id]
            if question.rating_scale_min and rating_value < question.rating_scale_min:
                raise ValidationError(f'Rating must be at least {question.rating_scale_min}')
            if question.rating_scale_max and rating_value > question.rating_scale_max:
                raise ValidationError(f'Rating must be at most {question.rating_scale_max}')

    with transaction.atomic():
        # Remove any existing response (re-submission guard)
        FeedbackResponse.objects.filter(task=task).delete()

        response = FeedbackResponse.objects.create(task=task, submitted_by=user)

        FeedbackAnswer.objects.bulk_create([
            FeedbackAnswer(
                response=response,
                question_id=a['question_id'],
                rating_value=a.get('rating_value'),
                text_value=a.get('text_value') or '',
            )
            for a in answers
        ])

        task.status        = 'SUBMITTED'
        task.draft_answers = None
        task.save(update_fields=['status', 'draft_answers', 'updated_at'])

    AuditLog.log(actor=user, action='SUBMIT_FEEDBACK',
                 entity_type='reviewer_task', entity_id=task_id,
                 new_value={
                     'reviewer': user.get_full_name(),
                     'reviewee': task.reviewee.get_full_name(),
                     'task_type': task.reviewer_type,
                     'cycle': task.cycle.name,
                 })

    return {'response_id': str(response.id), 'task_id': str(task_id)}


# ─── Aggregation Pipeline ─────────────────────────────────────────────────────

def aggregate_cycle(cycle):
    """
    Calculate overall / self / manager / peer scores for every participant.
    Idempotent — safe to run multiple times (uses update_or_create).
    """
    participants = CycleParticipant.objects.filter(cycle=cycle).select_related('user')

    for participant in participants:
        reviewee = participant.user

        def avg_score(reviewer_type):
            tasks = ReviewerTask.objects.filter(
                cycle=cycle, reviewee=reviewee,
                reviewer_type=reviewer_type, status='SUBMITTED'
            )
            responses = FeedbackResponse.objects.filter(task__in=tasks)
            result = FeedbackAnswer.objects.filter(
                response__in=responses, rating_value__isnull=False
            ).aggregate(avg=Avg('rating_value'))
            return result['avg']

        all_tasks     = ReviewerTask.objects.filter(cycle=cycle, reviewee=reviewee, status='SUBMITTED')
        all_responses = FeedbackResponse.objects.filter(task__in=all_tasks)
        overall_avg   = FeedbackAnswer.objects.filter(
            response__in=all_responses, rating_value__isnull=False
        ).aggregate(avg=Avg('rating_value'))['avg']

        AggregatedResult.objects.update_or_create(
            cycle=cycle,
            reviewee=reviewee,
            defaults={
                'overall_score': overall_avg,
                'self_score':    avg_score('SELF'),
                'manager_score': avg_score('MANAGER'),
                'peer_score':    avg_score('PEER'),
            }
        )


# ─── Report Helpers ───────────────────────────────────────────────────────────

def _get_feedback_sections(cycle, reviewee, viewer_role, viewer):
    """
    Builds the detailed feedback sections for a report.
    Applies anonymity rules — hides reviewer identity for ANONYMOUS tasks.
    """
    tasks = ReviewerTask.objects.filter(
        cycle=cycle, reviewee=reviewee, status='SUBMITTED'
    ).select_related('reviewer')

    sections = []
    for task in tasks:
        response = FeedbackResponse.objects.filter(task=task).first()
        if not response:
            continue

        answers = FeedbackAnswer.objects.filter(response=response).select_related('question')

        # Determine identity visibility based on anonymity mode
        show_identity = (
            task.anonymity_mode == 'TRANSPARENT'
            or viewer_role in ['SUPER_ADMIN', 'HR_ADMIN']
            or task.reviewer == viewer
        )

        sections.append({
            'reviewer_type': task.reviewer_type,
            'anonymity_mode': task.anonymity_mode,
            'hidden': not show_identity,
            'identity': {
                'id':         str(task.reviewer.id),
                'first_name': task.reviewer.first_name,
                'last_name':  task.reviewer.last_name,
            } if show_identity else None,
            'answers': [
                {
                    'question_id':   str(a.question_id),
                    'question_text': a.question.question_text,
                    'question_type': a.question.type,
                    'rating_value':  float(a.rating_value) if a.rating_value is not None else None,
                    'text_value':    a.text_value,
                }
                for a in answers
            ]
        })

    return sections


# ─── My Report (Employee) ─────────────────────────────────────────────────────

def get_my_report(cycle_id, user):
    try:
        cycle = ReviewCycle.objects.get(id=cycle_id)
    except ReviewCycle.DoesNotExist:
        raise NotFound('Cycle not found')

    if cycle.state not in ['RESULTS_RELEASED', 'ARCHIVED']:
        raise PermissionDenied('Results are not yet released')

    if not CycleParticipant.objects.filter(cycle=cycle, user=user).exists():
        raise PermissionDenied('You are not a participant in this cycle')

    try:
        aggregated = AggregatedResult.objects.get(cycle=cycle, reviewee=user)
    except AggregatedResult.DoesNotExist:
        aggregated = None

    sections = _get_feedback_sections(cycle, user, user.role, user)

    return {
        'cycle_id':      str(cycle_id),
        'cycle_name':    cycle.name,
        'reviewee':      {'id': str(user.id), 'name': user.get_full_name()},
        'overall_score': float(aggregated.overall_score) if aggregated and aggregated.overall_score else None,
        'self_score':    float(aggregated.self_score)    if aggregated and aggregated.self_score    else None,
        'manager_score': float(aggregated.manager_score) if aggregated and aggregated.manager_score else None,
        'peer_score':    float(aggregated.peer_score)    if aggregated and aggregated.peer_score    else None,
        'sections':      sections,
    }


# ─── Employee Report (Manager / HR / Super Admin) ─────────────────────────────

def get_employee_report(cycle_id, employee_id, viewer):
    try:
        cycle = ReviewCycle.objects.get(id=cycle_id)
    except ReviewCycle.DoesNotExist:
        raise NotFound('Cycle not found')

    if cycle.state not in ['RESULTS_RELEASED', 'ARCHIVED']:
        raise PermissionDenied('Results are not yet released')

    from apps.users.models import User
    try:
        employee = User.objects.get(id=employee_id)
    except User.DoesNotExist:
        raise NotFound('Employee not found')

    # Manager scope check — can only view direct reports
    if viewer.role == 'MANAGER':
        try:
            if employee.manager_relation.manager != viewer:
                raise PermissionDenied('Employee is not in your team')
        except Exception:
            raise PermissionDenied('Employee is not in your team')

    try:
        aggregated = AggregatedResult.objects.get(cycle=cycle, reviewee=employee)
    except AggregatedResult.DoesNotExist:
        aggregated = None

    sections = _get_feedback_sections(cycle, employee, viewer.role, viewer)

    AuditLog.log(actor=viewer, action='VIEW_REPORT', entity_type='report',
                 entity_id=cycle_id, new_value={
                     'viewed_by': viewer.get_full_name(),
                     'viewer_role': viewer.role,
                     'reviewee': employee.get_full_name(),
                     'cycle': cycle.name,
                 })

    return {
        'cycle_id':      str(cycle_id),
        'cycle_name':    cycle.name,
        'reviewee':      {'id': str(employee.id), 'name': employee.get_full_name(), 'email': employee.email},
        'overall_score': float(aggregated.overall_score) if aggregated and aggregated.overall_score else None,
        'self_score':    float(aggregated.self_score)    if aggregated and aggregated.self_score    else None,
        'manager_score': float(aggregated.manager_score) if aggregated and aggregated.manager_score else None,
        'peer_score':    float(aggregated.peer_score)    if aggregated and aggregated.peer_score    else None,
        'sections':      sections,
    }


# ─── Excel Export (Super Admin) ───────────────────────────────────────────────

def export_employee_report_excel(cycle_id, employee_id, actor):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from io import BytesIO

    report = get_employee_report(cycle_id, employee_id, actor)

    from apps.users.models import User
    from apps.review_cycles.models import ReviewCycle
    employee = User.objects.get(id=employee_id)
    cycle    = ReviewCycle.objects.get(id=cycle_id)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = '360 Report'

    header_font  = Font(bold=True, size=12)
    section_font = Font(bold=True, size=11)
    header_fill  = PatternFill('solid', fgColor='1677FF')
    header_font_white = Font(bold=True, color='FFFFFF')

    # ── Title block
    ws.append(['360° Feedback Report'])
    ws['A1'].font = Font(bold=True, size=14)
    ws.append(['Cycle',     cycle.name])
    ws.append(['Employee',  employee.get_full_name()])
    ws.append(['Email',     employee.email])
    ws.append(['Job Title', employee.job_title or ''])
    ws.append([])

    # ── Score Summary
    ws.append(['Score Summary'])
    ws[f'A{ws.max_row}'].font = section_font
    ws.append([
        'Overall', report['overall_score'] or '—',
        'Self',    report['self_score']    or '—',
        'Manager', report['manager_score'] or '—',
        'Peer',    report['peer_score']    or '—',
    ])
    ws.append([])

    # ── Detailed Answers header
    header_row = ws.max_row + 1
    ws.append(['Reviewer Type', 'Reviewer', 'Question', 'Rating', 'Text Response'])
    for col in range(1, 6):
        cell = ws.cell(row=header_row, column=col)
        cell.font  = header_font_white
        cell.fill  = header_fill
        cell.alignment = Alignment(horizontal='center')

    # ── Rows
    for section in report.get('sections', []):
        if section.get('hidden'):
            reviewer_name = 'Anonymous'
        else:
            identity = section.get('identity') or {}
            reviewer_name = f"{identity.get('first_name', '')} {identity.get('last_name', '')}".strip() or 'Unknown'

        for ans in section.get('answers', []):
            ws.append([
                section['reviewer_type'],
                reviewer_name,
                ans['question_text'],
                ans['rating_value'] if ans['rating_value'] is not None else '',
                ans['text_value'] or '',
            ])

    # ── Column widths
    ws.column_dimensions['A'].width = 16
    ws.column_dimensions['B'].width = 22
    ws.column_dimensions['C'].width = 50
    ws.column_dimensions['D'].width = 10
    ws.column_dimensions['E'].width = 40

    AuditLog.log(actor=actor, action='EXPORT_REPORT', entity_type='report',
                 entity_id=cycle_id, new_value={
                     'exported_by': actor.get_full_name(),
                     'reviewee': employee.get_full_name(),
                     'cycle': cycle.name,
                     'format': 'xlsx',
                 })

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


# ─── Bulk Excel Export — All Reports for a Cycle ──────────────────────────────

def export_all_reports_excel(cycle_id, actor):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from io import BytesIO

    from apps.users.models import User
    from apps.review_cycles.models import ReviewCycle, CycleParticipant
    from .models import AggregatedResult

    cycle        = ReviewCycle.objects.get(id=cycle_id)
    participants = CycleParticipant.objects.filter(cycle=cycle).select_related('user')
    employees    = [p.user for p in participants]

    results_map = {
        str(r.reviewee_id): r
        for r in AggregatedResult.objects.filter(cycle=cycle, reviewee__in=employees)
    }

    header_fill       = PatternFill('solid', fgColor='1677FF')
    header_font_white = Font(bold=True, color='FFFFFF')
    bold              = Font(bold=True)

    wb = openpyxl.Workbook()

    # ── Summary sheet ────────────────────────────────────────────────────────
    ws_summary = wb.active
    ws_summary.title = 'Summary'

    summary_headers = ['Name', 'Email', 'Department', 'Overall', 'Self', 'Manager', 'Peer']
    ws_summary.append(summary_headers)
    for col_idx, _ in enumerate(summary_headers, 1):
        cell = ws_summary.cell(row=1, column=col_idx)
        cell.font  = header_font_white
        cell.fill  = header_fill
        cell.alignment = Alignment(horizontal='center')

    for emp in employees:
        r = results_map.get(str(emp.id))
        ws_summary.append([
            emp.get_full_name(),
            emp.email,
            emp.department.name if emp.department else '',
            float(r.overall_score) if r and r.overall_score else '',
            float(r.self_score)    if r and r.self_score    else '',
            float(r.manager_score) if r and r.manager_score else '',
            float(r.peer_score)    if r and r.peer_score    else '',
        ])

    for col in ['A','B','C','D','E','F','G']:
        ws_summary.column_dimensions[col].width = 22

    # ── Per-employee sheets ──────────────────────────────────────────────────
    for emp in employees:
        sheet_name = emp.get_full_name()[:28]  # Excel sheet name limit
        ws = wb.create_sheet(title=sheet_name)

        ws.append(['360° Feedback Report'])
        ws['A1'].font = Font(bold=True, size=13)
        ws.append(['Cycle',     cycle.name])
        ws.append(['Employee',  emp.get_full_name()])
        ws.append(['Email',     emp.email])
        ws.append([])

        r = results_map.get(str(emp.id))
        ws.append(['Score Summary'])
        ws[f'A{ws.max_row}'].font = bold
        ws.append([
            'Overall', float(r.overall_score) if r and r.overall_score else '—',
            'Self',    float(r.self_score)    if r and r.self_score    else '—',
            'Manager', float(r.manager_score) if r and r.manager_score else '—',
            'Peer',    float(r.peer_score)    if r and r.peer_score    else '—',
        ])
        ws.append([])

        header_row = ws.max_row + 1
        ws.append(['Reviewer Type', 'Reviewer', 'Question', 'Rating', 'Text Response'])
        for col_idx in range(1, 6):
            cell = ws.cell(row=header_row, column=col_idx)
            cell.font  = header_font_white
            cell.fill  = header_fill
            cell.alignment = Alignment(horizontal='center')

        sections = _get_feedback_sections(cycle, emp, actor.role, actor)
        for section in sections:
            if section.get('hidden'):
                reviewer_name = 'Anonymous'
            else:
                identity = section.get('identity') or {}
                reviewer_name = f"{identity.get('first_name','')} {identity.get('last_name','')}".strip() or 'Unknown'
            for ans in section.get('answers', []):
                ws.append([
                    section['reviewer_type'],
                    reviewer_name,
                    ans['question_text'],
                    ans['rating_value'] if ans['rating_value'] is not None else '',
                    ans['text_value'] or '',
                ])

        ws.column_dimensions['A'].width = 16
        ws.column_dimensions['B'].width = 22
        ws.column_dimensions['C'].width = 50
        ws.column_dimensions['D'].width = 10
        ws.column_dimensions['E'].width = 40

    AuditLog.log(actor=actor, action='EXPORT_REPORT', entity_type='report',
                 entity_id=cycle_id, new_value={
                     'exported_by': actor.get_full_name(),
                     'cycle': cycle.name,
                     'type': 'bulk_all',
                     'count': len(employees),
                 })

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer, cycle.name
