"""
Phase 1 Parity Test Suite — AI Chat Assistant
===============================================
Goal: Prove that every chat command returns data that is consistent with
      the corresponding UI API endpoint.

Test strategy:
  - Each test class covers one chat command.
  - Tests create isolated, minimal data inside a DB transaction using
    pytest fixtures (no dependency on pre-existing seeded data).
  - For every command we verify:
      (a) Chat API returns HTTP 200 and status == 'success'
      (b) Chat response data matches the same data from the UI API
      (c) RBAC: unauthorised roles are blocked (status == 'rejected')
      (d) Unknown / unrecognised intent returns status == 'clarify'

Test users (created fresh per test via fixtures):
  - super_admin  / SUPER_ADMIN
  - hr_admin     / HR_ADMIN
  - manager_user / MANAGER
  - emp_user     / EMPLOYEE
  - emp2_user    / EMPLOYEE  (second employee, for relations)
"""

import uuid
import pytest
from decimal import Decimal
from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APIClient

from apps.users.models import User, Department, OrgHierarchy
from apps.review_cycles.models import (
    ReviewCycle, Template, TemplateSection, TemplateQuestion, CycleParticipant,
)
from apps.reviewer_workflow.models import ReviewerTask, PeerNomination
from apps.feedback.models import AggregatedResult
from apps.announcements.models import Announcement
from apps.audit.models import AuditLog


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

PASSWORD = 'Test@Parity1'
CHAT_URL = '/api/v1/chat/message/'
CONFIRM_URL = '/api/v1/chat/confirm/'


def make_user(email, role, dept=None, manager=None):
    user = User.objects.create_user(
        email=email,
        password=PASSWORD,
        first_name='Test',
        last_name=role.title(),
        role=role,
        department=dept,
        status='ACTIVE',
    )
    if manager:
        OrgHierarchy.objects.create(employee=user, manager=manager)
    return user


def auth_client(user):
    """Return an authenticated APIClient for the given user."""
    c = APIClient()
    resp = c.post(
        '/api/v1/auth/login/',
        {'email': user.email, 'password': PASSWORD},
        format='json',
    )
    assert resp.status_code == 200, f'Login failed for {user.email}: {resp.data}'
    c.credentials(HTTP_AUTHORIZATION=f'Bearer {resp.data["access"]}')
    return c


def chat(client, message, session_id=None):
    """POST a message to the chat API and return the response."""
    payload = {'message': message}
    if session_id:
        payload['session_id'] = session_id
    else:
        payload['session_id'] = str(uuid.uuid4())
    return client.post(CHAT_URL, payload, format='json')


def confirm(client, session_id, confirmed=True):
    """POST a confirmation to the chat confirm API."""
    return client.post(
        CONFIRM_URL,
        {'session_id': session_id, 'confirmed': confirmed},
        format='json',
    )


def make_template(hr_user, name='Test Template'):
    tmpl = Template.objects.create(name=name, created_by=hr_user)
    section = TemplateSection.objects.create(
        template=tmpl, title='Section', display_order=1
    )
    TemplateQuestion.objects.create(
        section=section,
        question_text='Rate overall performance?',
        type='RATING',
        display_order=1,
        is_required=True,
        rating_scale_min=1,
        rating_scale_max=5,
    )
    return tmpl


def make_cycle(
    hr_user, tmpl, name='Test Cycle', state='ACTIVE',
    peer_enabled=False, nomination=False,
):
    now = timezone.now()
    cycle = ReviewCycle.objects.create(
        name=name,
        template=tmpl,
        state=state,
        peer_enabled=peer_enabled,
        review_deadline=now + timedelta(days=14),
        nomination_deadline=now + timedelta(days=2) if nomination else None,
        created_by=hr_user,
    )
    return cycle


# ─────────────────────────────────────────────────────────────────────────────
# Shared fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def dept(db):
    return Department.objects.create(name=f'Dept-{uuid.uuid4().hex[:6]}')


@pytest.fixture
def super_admin(db, dept):
    return make_user(f'sa-{uuid.uuid4().hex[:6]}@test.com', 'SUPER_ADMIN', dept)


@pytest.fixture
def hr_admin(db, dept):
    return make_user(f'hr-{uuid.uuid4().hex[:6]}@test.com', 'HR_ADMIN', dept)


@pytest.fixture
def manager_user(db, dept):
    return make_user(f'mgr-{uuid.uuid4().hex[:6]}@test.com', 'MANAGER', dept)


@pytest.fixture
def emp_user(db, dept, manager_user):
    return make_user(
        f'emp-{uuid.uuid4().hex[:6]}@test.com', 'EMPLOYEE', dept, manager=manager_user
    )


@pytest.fixture
def emp2_user(db, dept, manager_user):
    return make_user(
        f'emp2-{uuid.uuid4().hex[:6]}@test.com', 'EMPLOYEE', dept, manager=manager_user
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. show_my_feedback
# ─────────────────────────────────────────────────────────────────────────────

class TestShowMyFeedback:
    """
    Parity: Chat 'show my feedback' vs GET /api/v1/feedback/cycles/{id}/my-report/
    Chat reads aggregated_results table directly; UI returns per-cycle report.
    Parity check: the cycle name and overall_score match.
    """

    def _setup(self, db, dept, hr_admin, emp_user):
        tmpl = make_template(hr_admin, 'Feedback-Tmpl')
        cycle = ReviewCycle.objects.create(
            name='Parity-Feedback-Cycle',
            template=tmpl,
            state='RESULTS_RELEASED',
            review_deadline=timezone.now() - timedelta(days=1),
            created_by=hr_admin,
        )
        CycleParticipant.objects.create(cycle=cycle, user=emp_user)
        AggregatedResult.objects.create(
            cycle=cycle,
            reviewee=emp_user,
            overall_score=Decimal('4.2'),
            peer_score=Decimal('4.0'),
            self_score=Decimal('4.5'),
            manager_score=Decimal('4.1'),
        )
        return cycle

    def test_chat_feedback_matches_db(self, db, dept, hr_admin, emp_user):
        """Chat returns feedback results that match what's in the DB."""
        self._setup(db, dept, hr_admin, emp_user)
        c = auth_client(emp_user)
        resp = chat(c, 'show my feedback')

        assert resp.status_code == 200, resp.data
        assert resp.data['status'] == 'success'
        assert resp.data['intent'] == 'show_my_feedback'

        results = resp.data['data']['results']
        assert len(results) >= 1, 'Expected at least 1 feedback result'

        match = next((r for r in results if r['cycle'] == 'Parity-Feedback-Cycle'), None)
        assert match is not None, 'Seeded cycle not found in chat feedback results'
        assert abs(match['overall_score'] - 4.2) < 0.01, f'Score mismatch: {match["overall_score"]}'

    def test_employee_rbac_allowed(self, db, dept, hr_admin, emp_user):
        """Employee is allowed to run show_my_feedback."""
        self._setup(db, dept, hr_admin, emp_user)
        c = auth_client(emp_user)
        resp = chat(c, 'show my feedback')
        assert resp.data['status'] in ('success',), 'Employee should be allowed'

    def test_no_feedback_returns_empty(self, db, dept, emp_user):
        """Employee with no results gets empty list, not an error."""
        c = auth_client(emp_user)
        resp = chat(c, 'show my feedback')
        assert resp.status_code == 200
        assert resp.data['status'] == 'success'
        assert resp.data['data']['results'] == []


# ─────────────────────────────────────────────────────────────────────────────
# 2. show_my_tasks
# ─────────────────────────────────────────────────────────────────────────────

class TestShowMyTasks:
    """
    Parity: Chat 'show my tasks' vs GET /api/v1/tasks/
    Both must report the same number of tasks assigned to the user.
    """

    def _setup(self, hr_admin, emp_user, emp2_user):
        tmpl = make_template(hr_admin, 'Tasks-Tmpl')
        cycle = make_cycle(hr_admin, tmpl, 'Parity-Tasks-Cycle')
        CycleParticipant.objects.create(cycle=cycle, user=emp_user)
        CycleParticipant.objects.create(cycle=cycle, user=emp2_user)
        # emp_user reviews emp2_user (PENDING) and has SELF (IN_PROGRESS)
        ReviewerTask.objects.create(
            cycle=cycle, reviewer=emp_user, reviewee=emp2_user,
            reviewer_type='PEER', status='PENDING',
        )
        ReviewerTask.objects.create(
            cycle=cycle, reviewer=emp_user, reviewee=emp_user,
            reviewer_type='SELF', status='IN_PROGRESS',
        )
        return cycle

    def test_chat_task_count_matches_ui(self, db, dept, hr_admin, emp_user, emp2_user):
        """Chat task count == UI /tasks/ task count for the same user."""
        self._setup(hr_admin, emp_user, emp2_user)

        # UI API count
        ui_client = auth_client(emp_user)
        ui_resp = ui_client.get('/api/v1/tasks/')
        assert ui_resp.status_code == 200, ui_resp.data
        ui_tasks = ui_resp.data.get('tasks', [])
        # Count only tasks where reviewer == emp_user
        ui_mine = [t for t in ui_tasks if str(t.get('reviewer_id', '')) == str(emp_user.id)
                   or t.get('reviewer_email') == emp_user.email]
        ui_count = len(ui_tasks)  # /tasks/ already filters to requesting user's tasks

        # Chat count
        chat_client = auth_client(emp_user)
        chat_resp = chat(chat_client, 'show my tasks')
        assert chat_resp.status_code == 200, chat_resp.data
        assert chat_resp.data['status'] == 'success'

        grouped = chat_resp.data['data']['grouped_tasks']
        chat_count = sum(len(g['tasks']) for g in grouped)

        assert chat_count == ui_count, (
            f'Task count mismatch — chat: {chat_count}, UI: {ui_count}'
        )

    def test_employee_rbac_allowed(self, db, dept, hr_admin, emp_user, emp2_user):
        """Employee is permitted to run show_my_tasks."""
        self._setup(hr_admin, emp_user, emp2_user)
        c = auth_client(emp_user)
        resp = chat(c, 'show my tasks')
        assert resp.data['status'] == 'success'

    def test_no_tasks_returns_empty(self, db, dept, emp_user):
        """User with no tasks gets success + empty grouped_tasks."""
        c = auth_client(emp_user)
        resp = chat(c, 'show my tasks')
        assert resp.status_code == 200
        assert resp.data['status'] == 'success'
        assert resp.data['data']['grouped_tasks'] == []


# ─────────────────────────────────────────────────────────────────────────────
# 3. show_pending_reviews
# ─────────────────────────────────────────────────────────────────────────────

class TestShowPendingReviews:
    """
    Parity: Chat 'show pending reviews' vs /tasks/ filtered to PENDING/IN_PROGRESS.
    Both must return only non-submitted tasks for the requesting user.
    """

    def _setup(self, hr_admin, emp_user, emp2_user):
        tmpl = make_template(hr_admin, 'Pending-Tmpl')
        cycle = make_cycle(hr_admin, tmpl, 'Parity-Pending-Cycle')
        ReviewerTask.objects.create(
            cycle=cycle, reviewer=emp_user, reviewee=emp2_user,
            reviewer_type='PEER', status='PENDING',
        )
        ReviewerTask.objects.create(
            cycle=cycle, reviewer=emp_user, reviewee=emp_user,
            reviewer_type='SELF', status='SUBMITTED',  # should NOT appear in pending
        )
        return cycle

    def test_only_pending_tasks_returned(self, db, dept, hr_admin, emp_user, emp2_user):
        """Chat pending reviews must NOT include already submitted tasks."""
        self._setup(hr_admin, emp_user, emp2_user)
        c = auth_client(emp_user)
        resp = chat(c, 'show pending reviews')

        assert resp.status_code == 200
        assert resp.data['status'] == 'success'

        grouped = resp.data['data']['grouped_tasks']
        all_statuses = [t['status'] for g in grouped for t in g['tasks']]
        for s in all_statuses:
            assert s in ('PENDING', 'IN_PROGRESS', 'CREATED'), (
                f"Unexpected status '{s}' in pending reviews — SUBMITTED tasks should be excluded"
            )

    def test_chat_pending_count_matches_ui(self, db, dept, hr_admin, emp_user, emp2_user):
        """Chat pending count == UI tasks with status in (PENDING, IN_PROGRESS, CREATED)."""
        self._setup(hr_admin, emp_user, emp2_user)

        ui_client = auth_client(emp_user)
        ui_resp = ui_client.get('/api/v1/tasks/')
        assert ui_resp.status_code == 200
        ui_pending = [
            t for t in ui_resp.data.get('tasks', [])
            if t.get('status') in ('PENDING', 'IN_PROGRESS', 'CREATED')
        ]

        chat_client = auth_client(emp_user)
        chat_resp = chat(chat_client, 'show pending reviews')
        assert chat_resp.data['status'] == 'success'

        grouped = chat_resp.data['data']['grouped_tasks']
        chat_pending_count = sum(len(g['tasks']) for g in grouped)

        assert chat_pending_count == len(ui_pending), (
            f'Pending count mismatch — chat: {chat_pending_count}, UI: {len(ui_pending)}'
        )

    def test_no_pending_tasks(self, db, dept, emp_user):
        """User with no pending tasks gets success + empty response."""
        c = auth_client(emp_user)
        resp = chat(c, 'show pending reviews')
        assert resp.data['status'] == 'success'
        assert resp.data['data']['grouped_tasks'] == []


# ─────────────────────────────────────────────────────────────────────────────
# 4. show_cycle_status
# ─────────────────────────────────────────────────────────────────────────────

class TestShowCycleStatus:
    """
    Parity: Chat 'show cycle status' vs GET /api/v1/cycles/
    Both must report the same cycles (by name and state).
    """

    def _setup(self, hr_admin):
        tmpl = make_template(hr_admin, 'Status-Tmpl')
        c1 = make_cycle(hr_admin, tmpl, 'Parity-Status-ACTIVE', state='ACTIVE')
        c2 = make_cycle(hr_admin, tmpl, 'Parity-Status-DRAFT', state='DRAFT')
        return c1, c2

    def test_chat_cycles_match_ui(self, db, dept, hr_admin):
        """Chat cycle names and states match UI /cycles/ response."""
        c1, c2 = self._setup(hr_admin)

        ui_client = auth_client(hr_admin)
        ui_resp = ui_client.get('/api/v1/cycles/')
        assert ui_resp.status_code == 200
        ui_cycles = {c['name']: c['state'] for c in ui_resp.data.get('cycles', [])}

        chat_client = auth_client(hr_admin)
        chat_resp = chat(chat_client, 'show cycle status')
        assert chat_resp.status_code == 200
        assert chat_resp.data['status'] == 'success'

        chat_cycles = {c['name']: c['state'] for c in chat_resp.data['data']['cycles']}

        # Every cycle in chat response must be in UI response with matching state
        for name, state in chat_cycles.items():
            assert name in ui_cycles, f"Cycle '{name}' in chat but not in UI"
            assert ui_cycles[name] == state, (
                f"State mismatch for '{name}': chat={state}, UI={ui_cycles[name]}"
            )

    def test_employee_blocked(self, db, dept, hr_admin, emp_user):
        """Employee must not access show_cycle_status (HR_ADMIN/MANAGER/SUPER_ADMIN only)."""
        self._setup(hr_admin)
        c = auth_client(emp_user)
        resp = chat(c, 'show cycle status')
        assert resp.data['status'] == 'rejected', (
            'Employee should be blocked from show_cycle_status'
        )

    def test_hr_admin_allowed(self, db, dept, hr_admin):
        """HR_ADMIN is permitted to run show_cycle_status."""
        self._setup(hr_admin)
        c = auth_client(hr_admin)
        resp = chat(c, 'show cycle status')
        assert resp.data['status'] == 'success'


# ─────────────────────────────────────────────────────────────────────────────
# 5. show_cycle_deadlines
# ─────────────────────────────────────────────────────────────────────────────

class TestShowCycleDeadlines:
    """
    Parity: Chat 'show cycle deadlines' shows cycles in ACTIVE/NOMINATION/FINALIZED
    state. The cycles must match those returned by the UI /cycles/ endpoint
    filtered to those same states.
    """

    def _setup(self, hr_admin):
        tmpl = make_template(hr_admin, 'Deadline-Tmpl')
        active = make_cycle(hr_admin, tmpl, 'Parity-Deadline-ACTIVE', state='ACTIVE')
        draft = make_cycle(hr_admin, tmpl, 'Parity-Deadline-DRAFT', state='DRAFT')
        return active, draft

    def test_only_open_cycles_in_deadlines(self, db, dept, hr_admin):
        """DRAFT cycles must NOT appear in deadline results."""
        active, draft = self._setup(hr_admin)
        c = auth_client(hr_admin)
        resp = chat(c, 'show cycle deadlines')

        assert resp.status_code == 200
        assert resp.data['status'] == 'success'

        names = [d['cycle'] for d in resp.data['data']['deadlines']]
        assert 'Parity-Deadline-ACTIVE' in names, 'ACTIVE cycle should be in deadlines'
        assert 'Parity-Deadline-DRAFT' not in names, 'DRAFT cycle must not appear in deadlines'

    def test_employee_can_see_deadlines(self, db, dept, hr_admin, emp_user):
        """Employee is permitted to see cycle deadlines."""
        self._setup(hr_admin)
        c = auth_client(emp_user)
        resp = chat(c, 'show cycle deadlines')
        assert resp.data['status'] == 'success'

    def test_deadline_count_matches_ui(self, db, dept, hr_admin):
        """Chat deadline count == UI /cycles/ count for ACTIVE/NOMINATION/FINALIZED."""
        self._setup(hr_admin)

        ui_client = auth_client(hr_admin)
        ui_resp = ui_client.get('/api/v1/cycles/')
        assert ui_resp.status_code == 200
        open_states = {'ACTIVE', 'NOMINATION', 'FINALIZED'}
        ui_open = [c for c in ui_resp.data.get('cycles', []) if c['state'] in open_states]

        chat_client = auth_client(hr_admin)
        chat_resp = chat(chat_client, 'show cycle deadlines')
        assert chat_resp.data['status'] == 'success'
        chat_count = len(chat_resp.data['data']['deadlines'])

        assert chat_count == len(ui_open), (
            f'Deadline count mismatch — chat: {chat_count}, UI open: {len(ui_open)}'
        )


# ─────────────────────────────────────────────────────────────────────────────
# 6. show_my_cycles
# ─────────────────────────────────────────────────────────────────────────────

class TestShowMyCycles:
    """
    Parity: Chat 'show my cycles' vs GET /api/v1/cycles/mine/
    Both must return the same cycles the user is a participant in.
    """

    def _setup(self, hr_admin, emp_user):
        tmpl = make_template(hr_admin, 'MyCycles-Tmpl')
        c1 = make_cycle(hr_admin, tmpl, 'Parity-MyCycle-1', state='ACTIVE')
        c2 = make_cycle(hr_admin, tmpl, 'Parity-MyCycle-2', state='NOMINATION')
        c3 = make_cycle(hr_admin, tmpl, 'Parity-Other-Cycle', state='ACTIVE')  # user NOT added

        CycleParticipant.objects.create(cycle=c1, user=emp_user)
        CycleParticipant.objects.create(cycle=c2, user=emp_user)
        return c1, c2, c3

    def test_chat_my_cycles_matches_ui(self, db, dept, hr_admin, emp_user):
        """Chat cycle names match exactly what /cycles/mine/ returns."""
        c1, c2, c3 = self._setup(hr_admin, emp_user)

        ui_client = auth_client(emp_user)
        ui_resp = ui_client.get('/api/v1/cycles/mine/')
        assert ui_resp.status_code == 200
        ui_names = {c['name'] for c in ui_resp.data.get('cycles', [])}

        chat_client = auth_client(emp_user)
        chat_resp = chat(chat_client, 'show my cycles')
        assert chat_resp.status_code == 200
        assert chat_resp.data['status'] == 'success'

        chat_names = {c['name'] for c in chat_resp.data['data']['cycles']}

        assert 'Parity-MyCycle-1' in chat_names
        assert 'Parity-MyCycle-2' in chat_names
        assert 'Parity-Other-Cycle' not in chat_names, (
            'User should NOT see cycles they are not a participant in'
        )
        assert chat_names == ui_names, (
            f'Cycle set mismatch — chat: {chat_names}, UI: {ui_names}'
        )

    def test_no_cycles_returns_empty(self, db, dept, emp_user):
        """User not in any cycle gets empty list."""
        c = auth_client(emp_user)
        resp = chat(c, 'show my cycles')
        assert resp.data['status'] == 'success'
        assert resp.data['data']['cycles'] == []


# ─────────────────────────────────────────────────────────────────────────────
# 7. show_my_nominations
# ─────────────────────────────────────────────────────────────────────────────

class TestShowMyNominations:
    """
    Parity: Chat 'show my nominations' vs
            GET /api/v1/tasks/cycles/{id}/nominations/
    Both must show the same nominations submitted by the user.
    """

    def _setup(self, hr_admin, emp_user, emp2_user):
        tmpl = make_template(hr_admin, 'Noms-Tmpl')
        cycle = make_cycle(
            hr_admin, tmpl, 'Parity-Nom-Cycle',
            state='NOMINATION', peer_enabled=True, nomination=True,
        )
        CycleParticipant.objects.create(cycle=cycle, user=emp_user)
        CycleParticipant.objects.create(cycle=cycle, user=emp2_user)

        PeerNomination.objects.create(
            cycle=cycle, reviewee=emp_user, peer=emp2_user,
            nominated_by=emp_user, status='PENDING',
        )
        return cycle

    def test_chat_nominations_match_ui(self, db, dept, hr_admin, emp_user, emp2_user):
        """Chat nominations match UI /nominations/ count."""
        cycle = self._setup(hr_admin, emp_user, emp2_user)

        ui_client = auth_client(emp_user)
        ui_resp = ui_client.get(f'/api/v1/tasks/cycles/{cycle.id}/nominations/')
        assert ui_resp.status_code == 200
        ui_count = len(ui_resp.data.get('nominations', []))

        chat_client = auth_client(emp_user)
        chat_resp = chat(chat_client, 'show my nominations')
        assert chat_resp.status_code == 200
        assert chat_resp.data['status'] == 'success'

        grouped = chat_resp.data['data']['grouped_nominations']
        chat_count = sum(len(g['nominations']) for g in grouped)

        assert chat_count >= 1, 'Expected at least 1 nomination'
        assert chat_count == ui_count, (
            f'Nomination count mismatch — chat: {chat_count}, UI: {ui_count}'
        )

    def test_nomination_peer_name_present(self, db, dept, hr_admin, emp_user, emp2_user):
        """Each nomination entry must contain peer name and status."""
        self._setup(hr_admin, emp_user, emp2_user)
        c = auth_client(emp_user)
        resp = chat(c, 'show my nominations')
        assert resp.data['status'] == 'success'

        grouped = resp.data['data']['grouped_nominations']
        for g in grouped:
            for nom in g['nominations']:
                assert 'peer' in nom and nom['peer'], 'Peer name missing'
                assert 'status' in nom and nom['status'], 'Status missing'

    def test_no_nominations_returns_empty(self, db, dept, emp_user):
        """User with no nominations gets empty result."""
        c = auth_client(emp_user)
        resp = chat(c, 'show my nominations')
        assert resp.data['status'] == 'success'
        assert resp.data['data']['grouped_nominations'] == []


# ─────────────────────────────────────────────────────────────────────────────
# 8. show_team_summary (Manager)
# ─────────────────────────────────────────────────────────────────────────────

class TestShowTeamSummary:
    """
    Parity: Chat 'show team summary' vs org_hierarchy DB.
    The number of team members in chat must match direct reports in DB.
    """

    def _setup(self, hr_admin, manager_user, emp_user, emp2_user):
        tmpl = make_template(hr_admin, 'Team-Tmpl')
        cycle = make_cycle(hr_admin, tmpl, 'Parity-Team-Cycle')
        return cycle

    def test_team_member_count_matches_hierarchy(self, db, dept, hr_admin,
                                                  manager_user, emp_user, emp2_user):
        """Chat team summary count == direct reports in OrgHierarchy."""
        self._setup(hr_admin, manager_user, emp_user, emp2_user)

        # OrgHierarchy fixture creates emp_user and emp2_user under manager_user
        db_count = OrgHierarchy.objects.filter(manager=manager_user).count()

        c = auth_client(manager_user)
        resp = chat(c, 'show team summary')
        assert resp.status_code == 200
        assert resp.data['status'] == 'success'

        chat_count = len(resp.data['data']['team'])
        assert chat_count == db_count, (
            f'Team count mismatch — chat: {chat_count}, DB hierarchy: {db_count}'
        )

    def test_employee_blocked_from_team_summary(self, db, dept, emp_user):
        """Employee must not access show_team_summary."""
        c = auth_client(emp_user)
        resp = chat(c, 'show team summary')
        assert resp.data['status'] == 'rejected', (
            'Employee should be blocked from show_team_summary'
        )

    def test_team_members_have_required_fields(self, db, dept, hr_admin,
                                                manager_user, emp_user, emp2_user):
        """Each team member entry must contain name, total_tasks, submitted."""
        self._setup(hr_admin, manager_user, emp_user, emp2_user)
        c = auth_client(manager_user)
        resp = chat(c, 'show team summary')
        assert resp.data['status'] == 'success'

        for member in resp.data['data']['team']:
            assert 'name' in member and member['name'], 'Missing name'
            assert 'total_tasks' in member, 'Missing total_tasks'
            assert 'submitted' in member, 'Missing submitted'


# ─────────────────────────────────────────────────────────────────────────────
# 9. show_team_nominations (Manager)
# ─────────────────────────────────────────────────────────────────────────────

class TestShowTeamNominations:
    """
    Parity: Chat 'show team nominations' vs DB PeerNomination for direct reports.
    """

    def _setup(self, hr_admin, manager_user, emp_user, emp2_user):
        tmpl = make_template(hr_admin, 'TeamNom-Tmpl')
        cycle = make_cycle(
            hr_admin, tmpl, 'Parity-TeamNom-Cycle',
            state='NOMINATION', peer_enabled=True, nomination=True,
        )
        CycleParticipant.objects.create(cycle=cycle, user=emp_user)
        CycleParticipant.objects.create(cycle=cycle, user=emp2_user)

        PeerNomination.objects.create(
            cycle=cycle, reviewee=emp_user, peer=emp2_user,
            nominated_by=emp_user, status='PENDING',
        )
        PeerNomination.objects.create(
            cycle=cycle, reviewee=emp2_user, peer=emp_user,
            nominated_by=emp2_user, status='APPROVED',
        )
        return cycle

    def test_chat_team_nominations_match_db(self, db, dept, hr_admin,
                                             manager_user, emp_user, emp2_user):
        """Chat team nominations count matches DB nominations for direct reports."""
        self._setup(hr_admin, manager_user, emp_user, emp2_user)

        # DB count: PENDING nominations where reviewee is a direct report of manager
        # Chat only shows PENDING (awaiting approval) — must match the same filter
        direct_report_ids = OrgHierarchy.objects.filter(
            manager=manager_user
        ).values_list('employee_id', flat=True)
        db_count = PeerNomination.objects.filter(
            reviewee_id__in=direct_report_ids,
            status='PENDING',
        ).count()

        c = auth_client(manager_user)
        resp = chat(c, 'show team nominations')
        assert resp.status_code == 200
        assert resp.data['status'] == 'success'

        grouped = resp.data['data']['grouped_team_nominations']
        chat_count = sum(len(g['nominations']) for g in grouped)

        assert chat_count == db_count, (
            f'Team nominations mismatch — chat: {chat_count}, DB: {db_count}'
        )

    def test_employee_blocked(self, db, dept, emp_user):
        """Employee must not access show_team_nominations."""
        c = auth_client(emp_user)
        resp = chat(c, 'show team nominations')
        assert resp.data['status'] == 'rejected'


# ─────────────────────────────────────────────────────────────────────────────
# 10. show_participation (HR_ADMIN)
# ─────────────────────────────────────────────────────────────────────────────

class TestShowParticipation:
    """
    Parity: Chat 'show participation stats' vs DB reviewer_tasks counts.
    Completion percentage must be correct.
    """

    def _setup(self, hr_admin, emp_user, emp2_user):
        tmpl = make_template(hr_admin, 'Participation-Tmpl')
        cycle = make_cycle(hr_admin, tmpl, 'Parity-Participation-Cycle', state='ACTIVE')
        # 2 tasks: 1 submitted, 1 pending
        ReviewerTask.objects.create(
            cycle=cycle, reviewer=emp_user, reviewee=emp2_user,
            reviewer_type='MANAGER', status='SUBMITTED',
        )
        ReviewerTask.objects.create(
            cycle=cycle, reviewer=emp2_user, reviewee=emp_user,
            reviewer_type='PEER', status='PENDING',
        )
        return cycle

    def test_chat_participation_matches_db(self, db, dept, hr_admin, emp_user, emp2_user):
        """Chat participation: submitted count and total match DB."""
        cycle = self._setup(hr_admin, emp_user, emp2_user)

        db_total = ReviewerTask.objects.filter(cycle=cycle).count()
        db_submitted = ReviewerTask.objects.filter(cycle=cycle, status='SUBMITTED').count()
        db_pct = round(db_submitted * 100.0 / db_total, 1) if db_total else 0

        c = auth_client(hr_admin)
        resp = chat(c, 'show participation stats')
        assert resp.status_code == 200
        assert resp.data['status'] == 'success'

        stats = resp.data['data']['participation']
        match = next((s for s in stats if s['cycle'] == 'Parity-Participation-Cycle'), None)
        assert match is not None, 'Seeded cycle not found in participation stats'
        assert match['total'] == db_total, f'Total mismatch: {match["total"]} vs {db_total}'
        assert match['submitted'] == db_submitted
        assert abs(match['completion_pct'] - db_pct) < 0.2, (
            f'Completion % mismatch: {match["completion_pct"]} vs {db_pct}'
        )

    def test_employee_blocked_from_participation(self, db, dept, emp_user):
        """Employee must not see participation stats."""
        c = auth_client(emp_user)
        resp = chat(c, 'show participation stats')
        assert resp.data['status'] == 'rejected'

    def test_manager_blocked_from_participation(self, db, dept, manager_user):
        """Manager must not see participation stats."""
        c = auth_client(manager_user)
        resp = chat(c, 'show participation stats')
        assert resp.data['status'] == 'rejected'


# ─────────────────────────────────────────────────────────────────────────────
# 11. show_templates (HR_ADMIN)
# ─────────────────────────────────────────────────────────────────────────────

class TestShowTemplates:
    """
    Parity: Chat 'show templates' vs GET /api/v1/cycles/templates/
    Same template names must appear in both.
    """

    def test_chat_templates_match_ui(self, db, dept, hr_admin):
        tmpl = make_template(hr_admin, 'Parity-Template-Alpha')

        ui_client = auth_client(hr_admin)
        ui_resp = ui_client.get('/api/v1/cycles/templates/')
        assert ui_resp.status_code == 200
        ui_names = {t['name'] for t in ui_resp.data.get('templates', [])}

        chat_client = auth_client(hr_admin)
        chat_resp = chat(chat_client, 'show all templates')
        assert chat_resp.status_code == 200
        assert chat_resp.data['status'] == 'success'

        chat_names = {t['name'] for t in chat_resp.data['data']['templates']}

        assert 'Parity-Template-Alpha' in chat_names, 'Seeded template missing from chat'
        # Every chat template must appear in the UI
        for name in chat_names:
            assert name in ui_names, f"Chat template '{name}' not in UI response"

    def test_employee_blocked_from_templates(self, db, dept, emp_user):
        """Employee must not access show_templates."""
        c = auth_client(emp_user)
        resp = chat(c, 'show all templates')
        assert resp.data['status'] == 'rejected'


# ─────────────────────────────────────────────────────────────────────────────
# 12. show_employees (HR_ADMIN / SUPER_ADMIN)
# ─────────────────────────────────────────────────────────────────────────────

class TestShowEmployees:
    """
    Parity: Chat 'show all employees' vs GET /api/v1/users/
    Both must return the same number of active users.
    """

    def test_chat_employee_count_matches_ui(self, db, dept, hr_admin, emp_user, emp2_user, super_admin):
        ui_client = auth_client(super_admin)
        ui_resp = ui_client.get('/api/v1/users/')
        assert ui_resp.status_code == 200
        ui_count = len(ui_resp.data.get('users', []))

        chat_client = auth_client(hr_admin)
        chat_resp = chat(chat_client, 'show all employees')
        assert chat_resp.status_code == 200
        assert chat_resp.data['status'] == 'success'

        chat_count = len(chat_resp.data['data']['employees'])
        assert chat_count == ui_count, (
            f'Employee count mismatch — chat: {chat_count}, UI: {ui_count}'
        )

    def test_employee_blocked_from_show_employees(self, db, dept, emp_user):
        """Employee must not access show_employees."""
        c = auth_client(emp_user)
        resp = chat(c, 'show all employees')
        assert resp.data['status'] == 'rejected'

    def test_manager_blocked_from_show_employees(self, db, dept, manager_user):
        """Manager must not access show_employees."""
        c = auth_client(manager_user)
        resp = chat(c, 'show all employees')
        assert resp.data['status'] == 'rejected'


# ─────────────────────────────────────────────────────────────────────────────
# 13. show_announcements
# ─────────────────────────────────────────────────────────────────────────────

class TestShowAnnouncements:
    """
    Parity: Chat 'show announcements' vs GET /api/v1/announcements/
    Both must return the same count of active, non-expired announcements.
    """

    def _setup(self, hr_admin):
        now = timezone.now()
        Announcement.objects.create(
            message='Parity: Q1 cycle is now open.',
            type='info',
            is_active=True,
            expires_at=now + timedelta(days=10),
            created_by=hr_admin,
        )
        Announcement.objects.create(
            message='Parity: Complete your self-review by Friday.',
            type='warning',
            is_active=True,
            expires_at=now + timedelta(days=3),
            created_by=hr_admin,
        )
        # Expired — must NOT appear
        Announcement.objects.create(
            message='Parity: Expired announcement.',
            type='info',
            is_active=True,
            expires_at=now - timedelta(days=1),
            created_by=hr_admin,
        )

    def test_chat_announcements_match_ui(self, db, dept, hr_admin, emp_user):
        self._setup(hr_admin)

        ui_client = auth_client(emp_user)
        ui_resp = ui_client.get('/api/v1/announcements/')
        assert ui_resp.status_code == 200
        ui_count = len(ui_resp.data.get('announcements', []))

        chat_client = auth_client(emp_user)
        chat_resp = chat(chat_client, 'show announcements')
        assert chat_resp.status_code == 200
        assert chat_resp.data['status'] == 'success'

        chat_count = len(chat_resp.data['data']['announcements'])
        assert chat_count == ui_count, (
            f'Announcement count mismatch — chat: {chat_count}, UI: {ui_count}'
        )

    def test_expired_announcements_excluded(self, db, dept, hr_admin, emp_user):
        """Expired announcements must not appear in chat response."""
        self._setup(hr_admin)
        c = auth_client(emp_user)
        resp = chat(c, 'show announcements')
        assert resp.data['status'] == 'success'

        messages = [a['message'] for a in resp.data['data']['announcements']]
        assert not any('Expired' in m for m in messages), (
            'Expired announcement must not appear in chat results'
        )

    def test_all_roles_can_see_announcements(self, db, dept, hr_admin,
                                              emp_user, manager_user, super_admin):
        self._setup(hr_admin)
        for user in (emp_user, manager_user, hr_admin, super_admin):
            c = auth_client(user)
            resp = chat(c, 'show announcements')
            assert resp.data['status'] == 'success', (
                f'Role {user.role} should be allowed to see announcements'
            )


# ─────────────────────────────────────────────────────────────────────────────
# 14. show_audit_logs (SUPER_ADMIN only)
# ─────────────────────────────────────────────────────────────────────────────

class TestShowAuditLogs:
    """
    Parity: Chat 'show audit logs' vs GET /api/v1/audit/
    Both must return the same number of audit log entries.
    """

    def _setup(self, super_admin):
        for i in range(3):
            AuditLog.objects.create(
                actor=super_admin,
                action_type='CREATE',
                entity_type=f'PARITY_entity_{i}',
            )

    def test_chat_audit_count_matches_ui(self, db, dept, super_admin):
        self._setup(super_admin)

        ui_client = auth_client(super_admin)
        ui_resp = ui_client.get('/api/v1/audit/')
        assert ui_resp.status_code == 200
        ui_count = len(ui_resp.data.get('logs', []))

        chat_client = auth_client(super_admin)
        chat_resp = chat(chat_client, 'show audit logs')
        assert chat_resp.status_code == 200
        assert chat_resp.data['status'] == 'success'

        chat_count = len(chat_resp.data['data']['audit_logs'])
        # Chat returns last 15; UI also returns recent logs — counts must match (≤ 15)
        assert chat_count == min(ui_count, 15), (
            f'Audit log count mismatch — chat: {chat_count}, UI (capped 15): {min(ui_count, 15)}'
        )

    def test_employee_blocked_from_audit(self, db, dept, emp_user):
        """Employee must not access audit logs."""
        c = auth_client(emp_user)
        resp = chat(c, 'show audit logs')
        assert resp.data['status'] == 'rejected'

    def test_manager_blocked_from_audit(self, db, dept, manager_user):
        """Manager must not access audit logs."""
        c = auth_client(manager_user)
        resp = chat(c, 'show audit logs')
        assert resp.data['status'] == 'rejected'

    def test_hr_admin_blocked_from_audit(self, db, dept, hr_admin):
        """HR_ADMIN must not access audit logs (SUPER_ADMIN only)."""
        c = auth_client(hr_admin)
        resp = chat(c, 'show audit logs')
        assert resp.data['status'] == 'rejected'

    def test_audit_entries_have_required_fields(self, db, dept, super_admin):
        """Each audit log entry must have actor, action, entity, at."""
        self._setup(super_admin)
        c = auth_client(super_admin)
        resp = chat(c, 'show audit logs')
        assert resp.data['status'] == 'success'

        for entry in resp.data['data']['audit_logs']:
            assert 'actor' in entry
            assert 'action' in entry
            assert 'entity' in entry
            assert 'at' in entry


# ─────────────────────────────────────────────────────────────────────────────
# 15. create_cycle (HR_ADMIN — action command with slot filling + confirmation)
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateCycle:
    """
    Parity: Chat 'create a cycle' → slot fill → confirm → cycle appears in UI /cycles/
    Verifies the full action command pipeline end-to-end.
    """

    def _ensure_template(self, hr_admin):
        tmpl = Template.objects.first()
        if not tmpl:
            tmpl = make_template(hr_admin, 'CreateCycle-Default-Tmpl')
        return tmpl

    def test_full_create_cycle_flow(self, db, dept, hr_admin):
        """Complete create_cycle: intent → slot fill → confirm → DB record created."""
        self._ensure_template(hr_admin)
        c = auth_client(hr_admin)
        sid = str(uuid.uuid4())

        # Step 1: Trigger intent
        resp1 = chat(c, 'create a cycle', session_id=sid)
        assert resp1.status_code == 200
        assert resp1.data['intent'] == 'create_cycle'
        assert resp1.data['status'] == 'needs_input', (
            f'Expected needs_input for slot filling, got: {resp1.data["status"]}'
        )
        assert resp1.data['needs_input'] is True

        # Step 2: Provide cycle name
        resp2 = chat(c, 'Parity Test Cycle Chat Created', session_id=sid)
        assert resp2.status_code == 200
        assert resp2.data['status'] in ('awaiting_confirmation', 'needs_input'), (
            f'Expected awaiting_confirmation or more questions, got: {resp2.data["status"]}'
        )

        # Step 3: Confirm
        resp3 = confirm(c, sid, confirmed=True)
        assert resp3.status_code == 200
        assert resp3.data['status'] == 'success', (
            f'Cycle creation failed: {resp3.data.get("message")}'
        )

        # Parity check: cycle must appear in UI /cycles/
        ui_resp = c.get('/api/v1/cycles/')
        assert ui_resp.status_code == 200
        ui_names = [cy['name'] for cy in ui_resp.data.get('cycles', [])]
        assert 'Parity Test Cycle Chat Created' in ui_names, (
            'Created cycle must appear in UI /cycles/ endpoint'
        )

        # Cycle must be in DRAFT state
        created_cycle = ReviewCycle.objects.get(name='Parity Test Cycle Chat Created')
        assert created_cycle.state == 'DRAFT', (
            f'Chat-created cycle must start as DRAFT, got: {created_cycle.state}'
        )
        assert created_cycle.created_by == hr_admin

    def test_cancel_create_cycle(self, db, dept, hr_admin):
        """Cancelling a create_cycle confirmation must not create a cycle."""
        self._ensure_template(hr_admin)
        c = auth_client(hr_admin)
        sid = str(uuid.uuid4())

        resp1 = chat(c, 'create a cycle', session_id=sid)
        assert resp1.data['intent'] == 'create_cycle'

        resp2 = chat(c, 'CancelledCycleParityTest', session_id=sid)
        if resp2.data['status'] == 'awaiting_confirmation':
            resp3 = confirm(c, sid, confirmed=False)
            assert resp3.data['status'] == 'cancelled'
            assert not ReviewCycle.objects.filter(name='CancelledCycleParityTest').exists(), (
                'Cycle must NOT be created when user cancels confirmation'
            )

    def test_employee_blocked_from_create_cycle(self, db, dept, hr_admin, emp_user):
        """Employee must not create cycles."""
        self._ensure_template(hr_admin)
        c = auth_client(emp_user)
        resp = chat(c, 'create a cycle')
        assert resp.data['status'] == 'rejected', (
            'Employee must be blocked from create_cycle'
        )

    def test_manager_blocked_from_create_cycle(self, db, dept, hr_admin, manager_user):
        """Manager must not create cycles."""
        self._ensure_template(hr_admin)
        c = auth_client(manager_user)
        resp = chat(c, 'create a cycle')
        assert resp.data['status'] == 'rejected', (
            'Manager must be blocked from create_cycle'
        )


# ─────────────────────────────────────────────────────────────────────────────
# 16. create_template (HR_ADMIN — action command)
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateTemplate:
    """
    Parity: Chat 'create a template' → slot fill → confirm → template in UI /templates/
    """

    def test_full_create_template_flow(self, db, dept, hr_admin):
        c = auth_client(hr_admin)
        sid = str(uuid.uuid4())

        resp1 = chat(c, 'create a template', session_id=sid)
        assert resp1.data['intent'] == 'create_template'
        assert resp1.data['status'] in ('needs_input', 'awaiting_confirmation')

        if resp1.data['status'] == 'needs_input':
            resp2 = chat(c, 'Parity Template Chat Created', session_id=sid)
            assert resp2.data['status'] == 'awaiting_confirmation'
        else:
            resp2 = resp1

        resp3 = confirm(c, sid, confirmed=True)
        assert resp3.status_code == 200
        assert resp3.data['status'] == 'success'

        # Parity: template must appear in UI
        ui_resp = c.get('/api/v1/cycles/templates/')
        assert ui_resp.status_code == 200
        ui_names = [t['name'] for t in ui_resp.data.get('templates', [])]
        assert 'Parity Template Chat Created' in ui_names, (
            'Created template must appear in UI /templates/ endpoint'
        )

    def test_employee_blocked_from_create_template(self, db, dept, emp_user):
        """Employee must not create templates."""
        c = auth_client(emp_user)
        resp = chat(c, 'create a template')
        assert resp.data['status'] == 'rejected'


# ─────────────────────────────────────────────────────────────────────────────
# 17. activate_cycle (HR_ADMIN — action command)
# ─────────────────────────────────────────────────────────────────────────────

class TestActivateCycle:
    """
    Parity: Chat 'activate cycle' → confirm → DB state = ACTIVE
    Compare with POST /api/v1/cycles/{id}/activate/
    """

    def _setup(self, hr_admin):
        tmpl = make_template(hr_admin, 'Activate-Tmpl')
        cycle = make_cycle(hr_admin, tmpl, 'Parity-Activate-Cycle', state='DRAFT')
        return cycle

    def test_chat_activate_changes_db_state(self, db, dept, hr_admin):
        """After chat activate + confirm, cycle state must be ACTIVE in DB."""
        cycle = self._setup(hr_admin)
        c = auth_client(hr_admin)
        sid = str(uuid.uuid4())

        # Step 1: trigger intent
        resp1 = chat(c, 'activate cycle', session_id=sid)
        assert resp1.data['intent'] == 'activate_cycle'

        # If cycle_id needed, provide cycle name
        if resp1.data['status'] == 'needs_input':
            resp2 = chat(c, cycle.name, session_id=sid)
            assert resp2.data['status'] == 'awaiting_confirmation', (
                f'Expected awaiting_confirmation, got: {resp2.data["status"]} / {resp2.data["message"]}'
            )
        else:
            resp2 = resp1

        # Confirm
        resp3 = confirm(c, sid, confirmed=True)
        assert resp3.status_code == 200
        assert resp3.data['status'] == 'success'

        # Parity: DB state must be ACTIVE
        cycle.refresh_from_db()
        assert cycle.state == 'ACTIVE', (
            f'Cycle state must be ACTIVE after chat activate, got: {cycle.state}'
        )

        # Parity: UI /cycles/{id}/ also reflects ACTIVE
        ui_resp = c.get(f'/api/v1/cycles/{cycle.id}/')
        assert ui_resp.status_code == 200
        assert ui_resp.data.get('cycle', {}).get('state') == 'ACTIVE', (
            'UI endpoint must also report ACTIVE state after chat activation'
        )

    def test_employee_blocked_from_activate(self, db, dept, hr_admin, emp_user):
        """Employee must not activate cycles."""
        c = auth_client(emp_user)
        resp = chat(c, 'activate cycle')
        assert resp.data['status'] == 'rejected'


# ─────────────────────────────────────────────────────────────────────────────
# 18. close_cycle (HR_ADMIN — action command)
# ─────────────────────────────────────────────────────────────────────────────

class TestCloseCycle:
    """
    Parity: Chat 'close cycle' → confirm → DB state = CLOSED
    Compare with POST /api/v1/cycles/{id}/close/
    """

    def _setup(self, hr_admin):
        tmpl = make_template(hr_admin, 'Close-Tmpl')
        cycle = make_cycle(hr_admin, tmpl, 'Parity-Close-Cycle', state='ACTIVE')
        return cycle

    def test_chat_close_changes_db_state(self, db, dept, hr_admin):
        """After chat close + confirm, cycle state must be CLOSED in DB."""
        cycle = self._setup(hr_admin)
        c = auth_client(hr_admin)
        sid = str(uuid.uuid4())

        resp1 = chat(c, 'close cycle', session_id=sid)
        assert resp1.data['intent'] == 'close_cycle'

        if resp1.data['status'] == 'needs_input':
            resp2 = chat(c, cycle.name, session_id=sid)
            assert resp2.data['status'] == 'awaiting_confirmation', (
                f'Expected awaiting_confirmation, got: {resp2.data}'
            )
        else:
            resp2 = resp1

        resp3 = confirm(c, sid, confirmed=True)
        assert resp3.status_code == 200
        assert resp3.data['status'] == 'success'

        cycle.refresh_from_db()
        assert cycle.state == 'CLOSED', (
            f'Cycle must be CLOSED after chat close, got: {cycle.state}'
        )

    def test_cannot_close_draft_cycle(self, db, dept, hr_admin):
        """Trying to close a DRAFT cycle must fail gracefully."""
        tmpl = make_template(hr_admin, 'CloseDraft-Tmpl')
        draft_cycle = make_cycle(hr_admin, tmpl, 'Parity-CloseDraft-Cycle', state='DRAFT')

        # Directly test the action command (bypassing slot filling for speed)
        from apps.chat_assistant.command_handlers.action_commands import CloseCycleCommand
        cmd = CloseCycleCommand()
        result = cmd.execute({'cycle_id': str(draft_cycle.id)}, hr_admin)
        assert result['success'] is False, 'Closing a DRAFT cycle must return success=False'


# ─────────────────────────────────────────────────────────────────────────────
# 19. cancel_cycle (HR_ADMIN — action command)
# ─────────────────────────────────────────────────────────────────────────────

class TestCancelCycle:
    """
    Parity: Chat 'cancel cycle' → confirm → DB state = ARCHIVED
    Compare with POST /api/v1/cycles/{id}/archive/
    """

    def _setup(self, hr_admin):
        tmpl = make_template(hr_admin, 'Cancel-Tmpl')
        cycle = make_cycle(hr_admin, tmpl, 'Parity-Cancel-Cycle', state='DRAFT')
        return cycle

    def test_chat_cancel_changes_db_state(self, db, dept, hr_admin):
        """After chat cancel + confirm, cycle state must be ARCHIVED in DB."""
        cycle = self._setup(hr_admin)
        c = auth_client(hr_admin)
        sid = str(uuid.uuid4())

        resp1 = chat(c, 'cancel cycle', session_id=sid)
        assert resp1.data['intent'] == 'cancel_cycle'

        if resp1.data['status'] == 'needs_input':
            resp2 = chat(c, cycle.name, session_id=sid)
            assert resp2.data['status'] == 'awaiting_confirmation', (
                f'Expected awaiting_confirmation, got: {resp2.data}'
            )
        else:
            resp2 = resp1

        resp3 = confirm(c, sid, confirmed=True)
        assert resp3.status_code == 200
        assert resp3.data['status'] == 'success'

        cycle.refresh_from_db()
        assert cycle.state == 'ARCHIVED', (
            f'Cycle must be ARCHIVED after chat cancel, got: {cycle.state}'
        )

    def test_cannot_cancel_closed_cycle(self, db, dept, hr_admin):
        """Trying to cancel a CLOSED cycle must fail gracefully."""
        tmpl = make_template(hr_admin, 'CancelClosed-Tmpl')
        closed_cycle = make_cycle(hr_admin, tmpl, 'Parity-CancelClosed-Cycle', state='CLOSED')

        from apps.chat_assistant.command_handlers.action_commands import CancelCycleCommand
        cmd = CancelCycleCommand()
        result = cmd.execute({'cycle_id': str(closed_cycle.id)}, hr_admin)
        assert result['success'] is False, 'Cancelling a CLOSED cycle must return success=False'


# ─────────────────────────────────────────────────────────────────────────────
# 20. release_results (HR_ADMIN — action command)
# ─────────────────────────────────────────────────────────────────────────────

class TestReleaseResults:
    """
    Parity: Chat 'release results' → confirm → DB state = RESULTS_RELEASED
    Compare with POST /api/v1/cycles/{id}/release-results/
    """

    def _setup(self, hr_admin):
        tmpl = make_template(hr_admin, 'Release-Tmpl')
        cycle = make_cycle(hr_admin, tmpl, 'Parity-Release-Cycle', state='CLOSED')
        return cycle

    def test_chat_release_changes_db_state(self, db, dept, hr_admin):
        """After chat release-results + confirm, DB state = RESULTS_RELEASED."""
        cycle = self._setup(hr_admin)
        c = auth_client(hr_admin)
        sid = str(uuid.uuid4())

        resp1 = chat(c, 'release results', session_id=sid)
        assert resp1.data['intent'] == 'release_results'

        if resp1.data['status'] == 'needs_input':
            resp2 = chat(c, cycle.name, session_id=sid)
            assert resp2.data['status'] == 'awaiting_confirmation', (
                f'Expected awaiting_confirmation, got: {resp2.data}'
            )
        else:
            resp2 = resp1

        resp3 = confirm(c, sid, confirmed=True)
        assert resp3.status_code == 200
        assert resp3.data['status'] == 'success'

        cycle.refresh_from_db()
        assert cycle.state == 'RESULTS_RELEASED', (
            f'Cycle must be RESULTS_RELEASED, got: {cycle.state}'
        )

    def test_cannot_release_active_cycle(self, db, dept, hr_admin):
        """Releasing results on ACTIVE cycle must fail gracefully."""
        tmpl = make_template(hr_admin, 'ReleaseActive-Tmpl')
        active_cycle = make_cycle(hr_admin, tmpl, 'Parity-ReleaseActive-Cycle', state='ACTIVE')

        from apps.chat_assistant.command_handlers.action_commands import ReleaseResultsCommand
        cmd = ReleaseResultsCommand()
        result = cmd.execute({'cycle_id': str(active_cycle.id)}, hr_admin)
        assert result['success'] is False, (
            'Releasing results on ACTIVE cycle must return success=False'
        )


# ─────────────────────────────────────────────────────────────────────────────
# 21. nominate_peers (EMPLOYEE — action command)
# ─────────────────────────────────────────────────────────────────────────────

class TestNominatePeers:
    """
    Parity: After chat nominate_peers + confirm, DB PeerNomination record exists.
    UI endpoint /nominations/ must also reflect the new nomination.
    """

    def _setup(self, hr_admin, emp_user, emp2_user):
        tmpl = make_template(hr_admin, 'NominatePeer-Tmpl')
        cycle = make_cycle(
            hr_admin, tmpl, 'Parity-NominatePeer-Cycle',
            state='NOMINATION', peer_enabled=True, nomination=True,
        )
        CycleParticipant.objects.create(cycle=cycle, user=emp_user)
        CycleParticipant.objects.create(cycle=cycle, user=emp2_user)
        return cycle

    def test_nomination_appears_in_db_and_ui(self, db, dept, hr_admin, emp_user, emp2_user):
        """After chat nomination, record exists in DB and UI /nominations/ endpoint."""
        cycle = self._setup(hr_admin, emp_user, emp2_user)

        from apps.chat_assistant.command_handlers.action_commands import NominatePeersCommand
        cmd = NominatePeersCommand()
        result = cmd.execute(
            {
                'cycle_id': str(cycle.id),
                'peer_emails': emp2_user.email,
            },
            emp_user,
        )
        assert result['success'] is True, f'Nomination failed: {result["message"]}'
        assert emp2_user.email in result['data']['nominated']

        # Parity: DB record must exist
        assert PeerNomination.objects.filter(
            cycle=cycle, reviewee=emp_user, peer=emp2_user
        ).exists(), 'PeerNomination must exist in DB after chat nomination'

        # Parity: UI nominations endpoint must also show it
        c = auth_client(emp_user)
        ui_resp = c.get(f'/api/v1/tasks/cycles/{cycle.id}/nominations/')
        assert ui_resp.status_code == 200
        # UI returns peer_email as a flat field (not nested object)
        ui_peers = [n.get('peer_email', '') for n in ui_resp.data.get('nominations', [])]
        assert emp2_user.email in ui_peers, (
            'Chat-created nomination must appear in UI /nominations/ endpoint'
        )

    def test_cannot_nominate_in_active_only_cycle(self, db, dept, hr_admin, emp_user, emp2_user):
        """Nominating in a DRAFT cycle must fail."""
        tmpl = make_template(hr_admin, 'NomDraft-Tmpl')
        draft_cycle = make_cycle(hr_admin, tmpl, 'Parity-NomDraft-Cycle', state='DRAFT')

        from apps.chat_assistant.command_handlers.action_commands import NominatePeersCommand
        cmd = NominatePeersCommand()
        result = cmd.execute(
            {'cycle_id': str(draft_cycle.id), 'peer_emails': emp2_user.email},
            emp_user,
        )
        assert result['success'] is False, (
            'Nominating in DRAFT cycle must fail'
        )


# ─────────────────────────────────────────────────────────────────────────────
# 22. RBAC — Cross-role boundary tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRBAC:
    """
    Verify that role-based access control is consistently enforced
    across all protected commands.
    """

    PROTECTED_COMMANDS = [
        # (chat_message, roles_that_must_be_rejected)
        ('create a cycle',           ['EMPLOYEE', 'MANAGER']),
        ('create a template',        ['EMPLOYEE', 'MANAGER']),
        ('show audit logs',          ['EMPLOYEE', 'MANAGER', 'HR_ADMIN']),
        ('show participation stats', ['EMPLOYEE', 'MANAGER']),
        ('show all employees',       ['EMPLOYEE', 'MANAGER']),
        ('show all templates',       ['EMPLOYEE', 'MANAGER']),
        ('show cycle status',        ['EMPLOYEE']),
        ('show team summary',        ['EMPLOYEE']),
        ('show team nominations',    ['EMPLOYEE']),
    ]

    @pytest.mark.parametrize('command,blocked_roles', PROTECTED_COMMANDS)
    def test_rbac_enforcement(self, command, blocked_roles, db, dept,
                               hr_admin, manager_user, emp_user, super_admin):
        role_map = {
            'EMPLOYEE':    emp_user,
            'MANAGER':     manager_user,
            'HR_ADMIN':    hr_admin,
            'SUPER_ADMIN': super_admin,
        }
        for role in blocked_roles:
            user = role_map[role]
            c = auth_client(user)
            resp = chat(c, command)
            assert resp.status_code == 200
            assert resp.data['status'] == 'rejected', (
                f"Role {role} must be REJECTED for command '{command}', "
                f"but got status: {resp.data['status']}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# 23. Chat API contract — intent, status, data shape
# ─────────────────────────────────────────────────────────────────────────────

class TestChatAPIContract:
    """
    Verify that all chat responses follow the expected API contract shape:
    { session_id, intent, status, message, data, needs_input }
    """

    REQUIRED_FIELDS = ('session_id', 'intent', 'status', 'message', 'data')

    def test_success_response_has_required_fields(self, db, dept, hr_admin):
        make_template(hr_admin, 'Contract-Tmpl')
        make_cycle(hr_admin, Template.objects.first(), 'Contract-Cycle')

        c = auth_client(hr_admin)
        resp = chat(c, 'show cycle status')
        assert resp.status_code == 200
        for field in self.REQUIRED_FIELDS:
            assert field in resp.data, f"Required field '{field}' missing from chat response"

    def test_unknown_intent_response_shape(self, db, dept, emp_user):
        """Unknown intent returns status='clarify' with helpful message."""
        c = auth_client(emp_user)
        resp = chat(c, 'xyzzy completely random input 12345')
        assert resp.status_code == 200
        assert resp.data['status'] == 'clarify'
        assert resp.data['intent'] == 'unknown'
        assert len(resp.data['message']) > 0, 'Clarification message must not be empty'

    def test_unauthenticated_request_rejected(self, db):
        """Unauthenticated chat requests must return 401."""
        c = APIClient()
        resp = c.post(CHAT_URL, {'message': 'show my tasks', 'session_id': 'x'}, format='json')
        assert resp.status_code == 401, (
            f'Unauthenticated request must return 401, got: {resp.status_code}'
        )

    def test_session_id_returned_in_response(self, db, dept, emp_user):
        """The response session_id must match the one sent by the client."""
        sid = str(uuid.uuid4())
        c = auth_client(emp_user)
        resp = chat(c, 'show my tasks', session_id=sid)
        assert resp.status_code == 200
        assert resp.data['session_id'] == sid, (
            f'session_id mismatch: sent {sid}, got {resp.data["session_id"]}'
        )

    def test_rate_limit_enforced(self, db, dept, emp_user):
        """After exceeding rate limit (10/min), must return 429."""
        c = auth_client(emp_user)
        responses = []
        # Send 12 messages fast — should hit rate limit by message 11
        for i in range(12):
            r = chat(c, f'show my tasks {i}', session_id=str(uuid.uuid4()))
            responses.append(r.status_code)

        assert 429 in responses, (
            'Rate limit must return HTTP 429 after exceeding 10 messages/minute'
        )

    def test_confirm_without_pending_session_returns_400(self, db, dept, emp_user):
        """Calling confirm with no pending action must return 400."""
        c = auth_client(emp_user)
        resp = confirm(c, str(uuid.uuid4()), confirmed=True)
        assert resp.status_code == 400, (
            'Confirm with no pending action must return 400'
        )
