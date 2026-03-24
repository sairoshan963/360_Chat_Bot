"""
Management command: seed_chat_data
Seeds realistic data to test every AI chat command for all roles.

Safe to re-run — wipes [CHAT] prefixed data and recreates everything.

Usage:
  python manage.py seed_chat_data

Prerequisite:
  python manage.py seed_users  (users must exist first)

What it creates:
  Cycles:
    [CHAT] Q1 2026 — Active    → ACTIVE  (has tasks, nominations, results)
    [CHAT] Q2 2026 — Ongoing   → ACTIVE  (has tasks, some pending)
    [CHAT] Q3 2026 — Upcoming  → NOMINATION  (peer nomination phase)

  Tasks:
    - emp1 reviews emp2, emp3 (one PENDING, one IN_PROGRESS)
    - emp1 has a SELF review (SUBMITTED)
    - manager1 reviews emp1, emp2 (PENDING)
    - manager2 reviews emp4, emp5 (PENDING)
    - emp4 reviews emp5 as PEER (IN_PROGRESS)

  Nominations:
    - emp1 → emp2 (APPROVED), emp1 → emp3 (PENDING)
    - emp4 → emp5 (APPROVED), emp5 → emp4 (REJECTED)
    - emp2 → emp1 (PENDING)

  AggregatedResults:
    - emp1 in Q1: overall=4.2, peer=4.0, self=4.5
    - emp2 in Q1: overall=3.8, peer=3.6, self=4.0
    - emp4 in Q1: overall=4.5, peer=4.3, self=4.7

  Announcements:
    - 3 active announcements (info, warning, success)

  AuditLogs:
    - 10 sample entries covering different action types
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model

User = get_user_model()

EMAILS = [
    'admin@gamyam.com',
    'hr@gamyam.com',
    'manager1@gamyam.com',
    'manager2@gamyam.com',
    'emp1@gamyam.com',
    'emp2@gamyam.com',
    'emp3@gamyam.com',
    'roshan.neelam@gamyam.co',
    'emp4@gamyam.com',
    'emp5@gamyam.com',
]


class Command(BaseCommand):
    help = 'Seed chat command test data — covers all AI assistant commands for all roles'

    def handle(self, *args, **options):
        self.stdout.write('\n🤖  Chat Data Seed Script\n')

        # Load users — skip missing ones gracefully
        self.U = {}
        for email in EMAILS:
            try:
                self.U[email] = User.objects.get(email=email)
            except User.DoesNotExist:
                self.stdout.write(self.style.WARNING(f'  ⚠ Skipping missing user: {email}'))

        required = ['admin@gamyam.com', 'hr@gamyam.com', 'manager1@gamyam.com',
                    'emp1@gamyam.com', 'emp2@gamyam.com', 'emp3@gamyam.com']
        missing_required = [e for e in required if e not in self.U]
        if missing_required:
            self.stdout.write(self.style.ERROR(
                f'Missing required users: {missing_required}\nRun "python manage.py seed_users" first.'
            ))
            return

        # Load template — use whichever exists
        from apps.review_cycles.models import Template
        self.template = (
            Template.objects.filter(name='Simple 360° Review').first()
            or Template.objects.filter(name='Standard 360° Review').first()
            or Template.objects.first()
        )
        if not self.template:
            self.stdout.write(self.style.ERROR(
                'No templates found. Run "python manage.py seed_users" first.'
            ))
            return

        self.stdout.write(f'  Using template: {self.template.name}')

        with transaction.atomic():
            self._cleanup()
            c1 = self._seed_active_cycle_q1()
            c2 = self._seed_active_cycle_q2()
            c3 = self._seed_nomination_cycle_q3()
            self._seed_announcements()
            self._seed_audit_logs()

        self._print_summary(c1, c2, c3)

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def _cleanup(self):
        from apps.review_cycles.models import ReviewCycle
        from apps.reviewer_workflow.models import ReviewerTask, PeerNomination
        from apps.feedback.models import AggregatedResult
        from apps.announcements.models import Announcement
        from apps.audit.models import AuditLog

        cycles = ReviewCycle.objects.filter(name__startswith='[CHAT]')
        cnt = cycles.count()

        ReviewerTask.objects.filter(cycle__in=cycles).delete()
        PeerNomination.objects.filter(cycle__in=cycles).delete()
        AggregatedResult.objects.filter(cycle__in=cycles).delete()
        cycles.delete()

        Announcement.objects.filter(message__startswith='[CHAT]').delete()
        AuditLog.objects.filter(entity_type__startswith='CHAT_').delete()

        if cnt:
            self.stdout.write(f'  🧹 Cleaned up {cnt} previous [CHAT] cycle(s)')

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _add_participants(self, cycle, user_emails):
        from apps.review_cycles.models import CycleParticipant
        for email in user_emails:
            if email in self.U:
                CycleParticipant.objects.get_or_create(cycle=cycle, user=self.U[email])

    def _add_task(self, cycle, reviewee_email, reviewer_email, reviewer_type, status='PENDING'):
        from apps.reviewer_workflow.models import ReviewerTask
        ReviewerTask.objects.get_or_create(
            cycle=cycle,
            reviewee=self.U[reviewee_email],
            reviewer=self.U[reviewer_email],
            defaults={
                'reviewer_type': reviewer_type,
                'anonymity_mode': 'TRANSPARENT',
                'status': status,
            },
        )

    def _add_nomination(self, cycle, reviewee_email, peer_email, status='PENDING', approved_by=None):
        from apps.reviewer_workflow.models import PeerNomination
        PeerNomination.objects.get_or_create(
            cycle=cycle,
            reviewee=self.U[reviewee_email],
            peer=self.U[peer_email],
            defaults={
                'nominated_by': self.U[reviewee_email],
                'status': status,
                'approved_by': self.U[approved_by] if approved_by else None,
                'approved_at': timezone.now() if status == 'APPROVED' else None,
            },
        )

    # ── Cycle 1: ACTIVE — Q1 2026 (main test cycle) ───────────────────────────

    def _seed_active_cycle_q1(self):
        from apps.review_cycles.models import ReviewCycle
        from apps.feedback.models import AggregatedResult

        self.stdout.write('\n⚡  Creating [CHAT] Q1 2026 — Active...')
        now = timezone.now()

        cycle = ReviewCycle.objects.create(
            name='[CHAT] Q1 2026 — Active',
            description='Q1 2026 performance review — currently open for submissions.',
            state='ACTIVE',
            template=self.template,
            peer_enabled=True,
            peer_min_count=2,
            peer_max_count=4,
            peer_anonymity='ANONYMOUS',
            manager_anonymity='TRANSPARENT',
            self_anonymity='TRANSPARENT',
            nomination_deadline=now - timedelta(days=3),
            review_deadline=now + timedelta(days=7),
            nomination_approval_mode='MANUAL',
            quarter='Q1',
            quarter_year=2026,
            created_by=self.U['hr@gamyam.com'],
        )

        roshan = 'roshan.neelam@gamyam.co'
        participants = [
            'emp1@gamyam.com', 'emp2@gamyam.com', 'emp3@gamyam.com',
            'emp4@gamyam.com', 'emp5@gamyam.com',
            'manager1@gamyam.com', 'manager2@gamyam.com', roshan,
        ]
        self._add_participants(cycle, participants)

        # Tasks — emp1 as reviewer
        self._add_task(cycle, 'emp2@gamyam.com', 'emp1@gamyam.com', 'PEER',    'PENDING')
        self._add_task(cycle, 'emp3@gamyam.com', 'emp1@gamyam.com', 'PEER',    'IN_PROGRESS')
        self._add_task(cycle, 'emp1@gamyam.com', 'emp1@gamyam.com', 'SELF',    'SUBMITTED')

        # Tasks — manager1 as reviewer
        self._add_task(cycle, 'emp1@gamyam.com', 'manager1@gamyam.com', 'MANAGER', 'PENDING')
        self._add_task(cycle, 'emp2@gamyam.com', 'manager1@gamyam.com', 'MANAGER', 'PENDING')
        self._add_task(cycle, 'emp3@gamyam.com', 'manager1@gamyam.com', 'MANAGER', 'IN_PROGRESS')

        # Tasks — manager2 as reviewer
        self._add_task(cycle, 'emp4@gamyam.com', 'manager2@gamyam.com', 'MANAGER', 'PENDING')
        self._add_task(cycle, 'emp5@gamyam.com', 'manager2@gamyam.com', 'MANAGER', 'PENDING')

        # Tasks — emp4 as peer reviewer
        self._add_task(cycle, 'emp5@gamyam.com', 'emp4@gamyam.com', 'PEER', 'IN_PROGRESS')

        # Tasks — Roshan as reviewer (so your account shows data)
        if roshan in self.U:
            self._add_task(cycle, 'emp1@gamyam.com', roshan, 'PEER',    'PENDING')
            self._add_task(cycle, 'emp2@gamyam.com', roshan, 'PEER',    'IN_PROGRESS')
            self._add_task(cycle, roshan,             roshan, 'SELF',   'PENDING')

        # Nominations
        self._add_nomination(cycle, 'emp1@gamyam.com', 'emp2@gamyam.com', 'APPROVED', 'manager1@gamyam.com')
        self._add_nomination(cycle, 'emp1@gamyam.com', 'emp3@gamyam.com', 'PENDING')
        self._add_nomination(cycle, 'emp2@gamyam.com', 'emp1@gamyam.com', 'PENDING')
        self._add_nomination(cycle, 'emp4@gamyam.com', 'emp5@gamyam.com', 'APPROVED', 'manager2@gamyam.com')
        self._add_nomination(cycle, 'emp5@gamyam.com', 'emp4@gamyam.com', 'REJECTED', 'manager2@gamyam.com')
        if roshan in self.U:
            self._add_nomination(cycle, roshan, 'emp1@gamyam.com', 'APPROVED', 'admin@gamyam.com')
            self._add_nomination(cycle, roshan, 'emp2@gamyam.com', 'PENDING')

        # Aggregated results
        AggregatedResult.objects.get_or_create(
            cycle=cycle, reviewee=self.U['emp1@gamyam.com'],
            defaults={'overall_score': Decimal('4.2'), 'peer_score': Decimal('4.0'), 'self_score': Decimal('4.5'), 'manager_score': Decimal('4.1')},
        )
        AggregatedResult.objects.get_or_create(
            cycle=cycle, reviewee=self.U['emp2@gamyam.com'],
            defaults={'overall_score': Decimal('3.8'), 'peer_score': Decimal('3.6'), 'self_score': Decimal('4.0'), 'manager_score': Decimal('3.8')},
        )
        AggregatedResult.objects.get_or_create(
            cycle=cycle, reviewee=self.U['emp4@gamyam.com'],
            defaults={'overall_score': Decimal('4.5'), 'peer_score': Decimal('4.3'), 'self_score': Decimal('4.7'), 'manager_score': Decimal('4.4')},
        )
        if roshan in self.U:
            AggregatedResult.objects.get_or_create(
                cycle=cycle, reviewee=self.U[roshan],
                defaults={'overall_score': Decimal('4.7'), 'peer_score': Decimal('4.6'), 'self_score': Decimal('4.8'), 'manager_score': Decimal('4.7')},
            )

        self.stdout.write('  ✓ Q1 2026 Active — tasks, nominations, results (incl. Roshan)')
        return cycle

    # ── Cycle 2: ACTIVE — Q2 2026 (second active cycle) ──────────────────────

    def _seed_active_cycle_q2(self):
        from apps.review_cycles.models import ReviewCycle

        self.stdout.write('\n⚡  Creating [CHAT] Q2 2026 — Ongoing...')
        now = timezone.now()

        cycle = ReviewCycle.objects.create(
            name='[CHAT] Q2 2026 — Ongoing',
            description='Q2 2026 mid-year review — just opened.',
            state='ACTIVE',
            template=self.template,
            peer_enabled=False,
            manager_anonymity='TRANSPARENT',
            self_anonymity='TRANSPARENT',
            review_deadline=now + timedelta(days=21),
            nomination_approval_mode='AUTO',
            quarter='Q2',
            quarter_year=2026,
            created_by=self.U['hr@gamyam.com'],
        )

        roshan = 'roshan.neelam@gamyam.co'
        participants = [
            'emp1@gamyam.com', 'emp2@gamyam.com', 'emp3@gamyam.com',
            'manager1@gamyam.com', roshan,
        ]
        self._add_participants(cycle, participants)

        # emp1 has tasks here too — shows grouped by cycle in chat
        self._add_task(cycle, 'emp1@gamyam.com', 'emp1@gamyam.com',     'SELF',    'PENDING')
        self._add_task(cycle, 'emp2@gamyam.com', 'emp1@gamyam.com',     'PEER',    'PENDING')
        self._add_task(cycle, 'emp1@gamyam.com', 'manager1@gamyam.com', 'MANAGER', 'PENDING')
        self._add_task(cycle, 'emp2@gamyam.com', 'manager1@gamyam.com', 'MANAGER', 'PENDING')
        self._add_task(cycle, 'emp3@gamyam.com', 'manager1@gamyam.com', 'MANAGER', 'PENDING')

        # Roshan tasks in Q2
        if roshan in self.U:
            self._add_task(cycle, roshan,             roshan,             'SELF',    'PENDING')
            self._add_task(cycle, 'emp1@gamyam.com',  roshan,             'PEER',    'PENDING')

        self.stdout.write('  ✓ Q2 2026 Ongoing — tasks (incl. Roshan)')
        return cycle

    # ── Cycle 3: NOMINATION — Q3 2026 ────────────────────────────────────────

    def _seed_nomination_cycle_q3(self):
        from apps.review_cycles.models import ReviewCycle

        self.stdout.write('\n🗳️   Creating [CHAT] Q3 2026 — Upcoming...')
        now = timezone.now()

        cycle = ReviewCycle.objects.create(
            name='[CHAT] Q3 2026 — Upcoming',
            description='Q3 2026 review cycle — in peer nomination phase.',
            state='NOMINATION',
            template=self.template,
            peer_enabled=True,
            peer_min_count=2,
            peer_max_count=4,
            peer_anonymity='ANONYMOUS',
            manager_anonymity='TRANSPARENT',
            self_anonymity='TRANSPARENT',
            nomination_deadline=now + timedelta(days=2),
            review_deadline=now + timedelta(days=30),
            nomination_approval_mode='MANUAL',
            quarter='Q3',
            quarter_year=2026,
            created_by=self.U['hr@gamyam.com'],
        )

        roshan = 'roshan.neelam@gamyam.co'
        participants = [
            'emp1@gamyam.com', 'emp2@gamyam.com', 'emp3@gamyam.com',
            'emp4@gamyam.com', 'emp5@gamyam.com',
            'manager1@gamyam.com', 'manager2@gamyam.com', roshan,
        ]
        self._add_participants(cycle, participants)

        # Nominations in various states
        self._add_nomination(cycle, 'emp1@gamyam.com', 'emp2@gamyam.com', 'PENDING')
        self._add_nomination(cycle, 'emp1@gamyam.com', 'emp3@gamyam.com', 'APPROVED', 'manager1@gamyam.com')
        self._add_nomination(cycle, 'emp3@gamyam.com', 'emp1@gamyam.com', 'PENDING')
        self._add_nomination(cycle, 'emp4@gamyam.com', 'emp5@gamyam.com', 'PENDING')
        self._add_nomination(cycle, 'emp5@gamyam.com', 'emp4@gamyam.com', 'APPROVED', 'manager2@gamyam.com')
        if roshan in self.U:
            self._add_nomination(cycle, roshan, 'emp1@gamyam.com', 'APPROVED', 'admin@gamyam.com')
            self._add_nomination(cycle, roshan, 'emp3@gamyam.com', 'PENDING')

        self.stdout.write('  ✓ Q3 2026 Nomination — nominations in mixed states (incl. Roshan)')
        return cycle

    # ── Announcements ─────────────────────────────────────────────────────────

    def _seed_announcements(self):
        from apps.announcements.models import Announcement

        now = timezone.now()
        announcements = [
            {
                'message': '[CHAT] Q2 2026 feedback cycle is now open. Please complete your self-review by 31 March 2026.',
                'type': 'info',
                'expires_at': now + timedelta(days=20),
            },
            {
                'message': '[CHAT] Q1 2026 results are now available. Visit My Report to view your 360° feedback scores.',
                'type': 'success',
                'expires_at': now + timedelta(days=14),
            },
            {
                'message': '[CHAT] Reminder: Peer nomination deadline for Q3 2026 is in 2 days. Nominate your peers now.',
                'type': 'warning',
                'expires_at': now + timedelta(days=2),
            },
        ]
        for a in announcements:
            Announcement.objects.create(
                message=a['message'],
                type=a['type'],
                is_active=True,
                expires_at=a['expires_at'],
                created_by=self.U['hr@gamyam.com'],
            )
        self.stdout.write('\n📢  Created 3 announcements (info, success, warning)')

    # ── Audit Logs ────────────────────────────────────────────────────────────

    def _seed_audit_logs(self):
        from apps.audit.models import AuditLog

        now = timezone.now()
        entries = [
            {'actor': 'hr@gamyam.com',      'action': 'CREATE',   'entity': 'CHAT_review_cycle'},
            {'actor': 'hr@gamyam.com',      'action': 'ACTIVATE', 'entity': 'CHAT_review_cycle'},
            {'actor': 'admin@gamyam.com',   'action': 'UPDATE',   'entity': 'CHAT_user'},
            {'actor': 'manager1@gamyam.com','action': 'APPROVE',  'entity': 'CHAT_nomination'},
            {'actor': 'manager2@gamyam.com','action': 'REJECT',   'entity': 'CHAT_nomination'},
            {'actor': 'emp1@gamyam.com',    'action': 'SUBMIT',   'entity': 'CHAT_feedback'},
            {'actor': 'hr@gamyam.com',      'action': 'RELEASE',  'entity': 'CHAT_results'},
            {'actor': 'admin@gamyam.com',   'action': 'CREATE',   'entity': 'CHAT_template'},
            {'actor': 'hr@gamyam.com',      'action': 'CLOSE',    'entity': 'CHAT_review_cycle'},
            {'actor': 'admin@gamyam.com',   'action': 'RESET_PW', 'entity': 'CHAT_user'},
        ]
        for i, e in enumerate(entries):
            AuditLog.objects.create(
                actor=self.U[e['actor']],
                action_type=e['action'],
                entity_type=e['entity'],
                created_at=now - timedelta(hours=i * 3),
            )
        self.stdout.write('📋  Created 10 audit log entries')

    # ── Summary ───────────────────────────────────────────────────────────────

    def _print_summary(self, c1, c2, c3):
        U = self.U
        self.stdout.write(self.style.SUCCESS(f"""
✅  Chat seed complete!

┌─────────────────────────────────────────────────────────────────────────┐
│  3 CHAT CYCLES CREATED                                                  │
├──────────────────────────────────┬──────────────────────────────────────┤
│  [CHAT] Q1 2026 — Active         │  ACTIVE  · deadline in 7 days        │
│  [CHAT] Q2 2026 — Ongoing        │  ACTIVE  · deadline in 21 days       │
│  [CHAT] Q3 2026 — Upcoming       │  NOMINATION · deadline in 30 days    │
└──────────────────────────────────┴──────────────────────────────────────┘

TEST EACH COMMAND AS:

  EMPLOYEE  (emp1@gamyam.com / Admin@123)
  ─────────────────────────────────────────────────────────────
  ✓ "show my tasks"          → 2 groups: Q1 (PEER x2+SELF), Q2 (PEER+SELF)
  ✓ "show pending reviews"   → Q1: emp2 PENDING, emp3 IN_PROGRESS
  ✓ "show my nominations"    → Q1: emp2 APPROVED, emp3 PENDING  |  Q3: emp2 PENDING, emp3 APPROVED
  ✓ "show cycles I am in"    → Q1, Q2, Q3 listed
  ✓ "show upcoming deadlines"→ all 3 cycles with deadlines
  ✓ "show announcements"     → 3 active announcements
  ✓ "show my feedback"       → Q1: overall 4.2, peer 4.0, self 4.5

  MANAGER  (manager1@gamyam.com / Admin@123)
  ─────────────────────────────────────────────────────────────
  ✓ "show pending reviews"   → Q1: emp1, emp2 PENDING | emp3 IN_PROGRESS
                               Q2: emp1, emp2, emp3 PENDING
  ✓ "show team summary"      → emp1, emp2, emp3 with task counts
  ✓ "show team nominations"  → emp1 group (emp2 APPROVED, emp3 PENDING)
  ✓ "show cycle status"      → Q1, Q2, Q3 listed

  HR_ADMIN  (hr@gamyam.com / Admin@123)
  ─────────────────────────────────────────────────────────────
  ✓ "show participation stats"→ Q1 and Q2 with completion %
  ✓ "show all templates"      → template(s) with cycle count
  ✓ "show all employees"      → all active users
  ✓ "create a cycle named Test Cycle" → confirmation → DRAFT created
  ✓ "create a template named Test Template" → confirmation → created

  SUPER_ADMIN  (admin@gamyam.com / Admin@123)
  ─────────────────────────────────────────────────────────────
  ✓ "show audit logs"         → 10 recent entries
  ✓ "activate cycle [CHAT] Q1 2026" → requires cycle to be DRAFT/NOMINATION
  ✓ "close cycle ..."         → requires ACTIVE state
"""))
