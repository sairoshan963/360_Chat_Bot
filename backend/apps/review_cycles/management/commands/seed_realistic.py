"""
Management command: seed_realistic
Wipes all existing demo data and seeds 10 realistic users across all roles,
2 rich templates, and 7 cycles covering every lifecycle state.

Usage:
    python manage.py seed_realistic

Roles created:
    SUPER_ADMIN  : admin@gamyam.com
    HR_ADMIN     : hr@gamyam.com, hr2@gamyam.com
    MANAGER      : manager1@gamyam.com (Engineering), manager2@gamyam.com (Product), manager3@gamyam.com (Design)
    EMPLOYEE     : emp1@gamyam.com, emp2@gamyam.com (Eng), emp3@gamyam.com (Product), emp4@gamyam.com (Design)

Cycles:
    1. Q3 2025 Annual Review         — ARCHIVED
    2. Q4 2025 Performance Review    — RESULTS_RELEASED  (full scores + aggregated)
    3. Q1 2026 Mid-Year Check-in     — CLOSED            (all feedback submitted)
    4. Q2 2026 Performance Review    — ACTIVE            (partial feedback)
    5. Q3 2026 Peer Nominations      — NOMINATION        (open, some pending/approved)
    6. Q4 2026 Leadership Assessment — FINALIZED         (nominations approved, tasks ready)
    7. FY2026 Company-Wide Review    — DRAFT
"""

import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

User = get_user_model()

PASSWORD = 'Admin@123'

# ── Users ──────────────────────────────────────────────────────────────────
USERS = [
    {'email': 'admin@gamyam.com',    'first': 'Super',   'last': 'Admin',    'role': 'SUPER_ADMIN', 'title': 'System Administrator', 'dept': 'HR'},
    {'email': 'hr@gamyam.com',       'first': 'Priya',   'last': 'Sharma',   'role': 'HR_ADMIN',    'title': 'HR Manager',           'dept': 'HR'},
    {'email': 'hr2@gamyam.com',      'first': 'Ananya',  'last': 'Reddy',    'role': 'HR_ADMIN',    'title': 'HR Business Partner',  'dept': 'HR'},
    {'email': 'manager1@gamyam.com', 'first': 'Ravi',    'last': 'Kumar',    'role': 'MANAGER',     'title': 'Engineering Manager',  'dept': 'Engineering'},
    {'email': 'manager2@gamyam.com', 'first': 'Deepa',   'last': 'Nair',     'role': 'MANAGER',     'title': 'Product Manager',      'dept': 'Product'},
    {'email': 'manager3@gamyam.com', 'first': 'Arjun',   'last': 'Singh',    'role': 'MANAGER',     'title': 'Design Lead',          'dept': 'Design'},
    {'email': 'emp1@gamyam.com',     'first': 'Kiran',   'last': 'Patel',    'role': 'EMPLOYEE',    'title': 'Software Engineer',    'dept': 'Engineering', 'manager': 'manager1@gamyam.com'},
    {'email': 'emp2@gamyam.com',     'first': 'Sneha',   'last': 'Gupta',    'role': 'EMPLOYEE',    'title': 'Senior Engineer',      'dept': 'Engineering', 'manager': 'manager1@gamyam.com'},
    {'email': 'emp3@gamyam.com',     'first': 'Rahul',   'last': 'Verma',    'role': 'EMPLOYEE',    'title': 'Product Analyst',      'dept': 'Product',     'manager': 'manager2@gamyam.com'},
    {'email': 'emp4@gamyam.com',     'first': 'Meera',   'last': 'Joshi',    'role': 'EMPLOYEE',    'title': 'UI/UX Designer',       'dept': 'Design',      'manager': 'manager3@gamyam.com'},
]

# ── Feedback answers per reviewer type ────────────────────────────────────
ANSWERS = {
    'SELF': {
        'ratings': [4, 4, 3, 4, 3, 4, 4, 3],
        'texts': [
            'I have strong backend experience and deliver features with good code quality.',
            'I communicate blockers proactively and document my work thoroughly.',
            'I collaborate well in sprints and enjoy code review sessions.',
            'My strength is problem decomposition and delivering under tight deadlines.',
            'I can improve on proactive knowledge sharing and mentoring juniors.',
            'I stay updated with industry trends and apply them in my work.',
            'Clear in written communication; could improve verbal presentation skills.',
            'Always willing to help teammates, though can sometimes over-commit.',
        ],
    },
    'MANAGER': {
        'ratings': [4, 5, 4, 5, 4, 3, 4, 4],
        'texts': [
            'Delivers high-quality work consistently and takes ownership of complex tasks.',
            'Communicates clearly; always keeps the team informed of progress.',
            'Excellent team player and goes beyond their scope to help others.',
            'Strong analytical skills and great attention to system design.',
            'Could delegate more and trust junior teammates on smaller tasks.',
            'Technically solid; would benefit from exploring newer tech stacks.',
            'Written communication is strong; growing comfort in large-group settings.',
            'One of our most reliable collaborators — sets a positive example.',
        ],
    },
    'PEER': {
        'ratings': [4, 4, 5, 5, 4, 4, 3, 5],
        'texts': [
            'Great technical depth, especially in debugging and architecture discussions.',
            'Always explains complex problems in simple terms — very approachable.',
            'Best collaborator I have worked with. Always supportive and available.',
            'Solid coder with a great eye for edge cases.',
            'Sometimes takes too long to review PRs but always thorough when they do.',
            'Up-to-date with best practices; shares useful articles and resources.',
            'Could be more vocal in team meetings; their insights are valuable.',
            'Makes every sprint better — team morale goes up when they are around.',
        ],
    },
    'DIRECT_REPORT': {
        'ratings': [3, 4, 4, 3, 4, 4, 3, 4],
        'texts': [
            'Has strong technical knowledge and guides us when we get stuck.',
            'Sets clear expectations and is easy to approach with questions.',
            'Encourages our ideas and values different perspectives.',
            'Leads by example; shows commitment to quality.',
            'More regular 1-on-1s would help us grow faster.',
            'Technically strong and helps us understand the bigger picture.',
            'Could improve on timely feedback for our work submissions.',
            'Very supportive of work-life balance — we appreciate that a lot.',
        ],
    },
}

# ── Template definitions ──────────────────────────────────────────────────
TEMPLATE_STANDARD = {
    'name': 'Standard 360° Review',
    'description': 'Comprehensive review covering technical skills, communication, collaboration, and leadership.',
    'sections': [
        {
            'title': 'Technical Skills',
            'questions': [
                {'text': 'How would you rate the quality of this person\'s technical work?', 'type': 'RATING'},
                {'text': 'How effectively does this person solve complex technical problems?', 'type': 'RATING'},
                {'text': 'Describe a specific example of strong or weak technical contribution.', 'type': 'TEXT'},
            ],
        },
        {
            'title': 'Communication',
            'questions': [
                {'text': 'How clearly does this person communicate ideas and updates?', 'type': 'RATING'},
                {'text': 'How well does this person listen and incorporate feedback?', 'type': 'RATING'},
                {'text': 'What can this person improve in their communication style?', 'type': 'TEXT'},
            ],
        },
        {
            'title': 'Collaboration & Teamwork',
            'questions': [
                {'text': 'How well does this person collaborate with others?', 'type': 'RATING'},
                {'text': 'How much does this person contribute to a positive team environment?', 'type': 'RATING'},
                {'text': 'What is this person\'s greatest strength as a team member?', 'type': 'TEXT'},
                {'text': 'What is one area where this person can grow to be a better collaborator?', 'type': 'TEXT'},
            ],
        },
    ],
}

TEMPLATE_LEADERSHIP = {
    'name': 'Leadership & Growth Review',
    'description': 'Focused on leadership qualities, strategic thinking, and personal growth potential.',
    'sections': [
        {
            'title': 'Leadership & Ownership',
            'questions': [
                {'text': 'How well does this person take ownership of outcomes?', 'type': 'RATING'},
                {'text': 'How effectively does this person lead initiatives or projects?', 'type': 'RATING'},
                {'text': 'Describe a moment this person showed strong or weak leadership.', 'type': 'TEXT'},
            ],
        },
        {
            'title': 'Strategic Thinking',
            'questions': [
                {'text': 'How well does this person think beyond day-to-day tasks?', 'type': 'RATING'},
                {'text': 'How effectively does this person prioritise what matters most?', 'type': 'RATING'},
                {'text': 'What strategic contribution has this person made recently?', 'type': 'TEXT'},
            ],
        },
        {
            'title': 'Growth & Learning',
            'questions': [
                {'text': 'How actively does this person seek to grow their skills?', 'type': 'RATING'},
                {'text': 'How open is this person to feedback and course-correction?', 'type': 'RATING'},
                {'text': 'What is one thing this person should focus on for their next level?', 'type': 'TEXT'},
                {'text': 'What is one achievement that best reflects their growth this period?', 'type': 'TEXT'},
            ],
        },
    ],
}


class Command(BaseCommand):
    help = 'Wipe all demo data and seed 10 realistic users + 7 cycles covering all states'

    def handle(self, *args, **options):
        self.stdout.write('\n🌱  Realistic Seed — 360 Feedback System\n')
        with transaction.atomic():
            self._flush()
            user_map   = self._seed_users()
            tmpl_map   = self._seed_templates(user_map)
            self._seed_cycles(user_map, tmpl_map)
        self.stdout.write(self.style.SUCCESS('\n✅  Done! All 10 users — password: Admin@123\n'))

    # ── Flush ──────────────────────────────────────────────────────────────

    def _flush(self):
        from apps.feedback.models import FeedbackAnswer, FeedbackResponse, AggregatedResult
        from apps.reviewer_workflow.models import ReviewerTask, PeerNomination
        from apps.review_cycles.models import ReviewCycle, CycleParticipant, Template, TemplateSection, TemplateQuestion
        from apps.users.models import OrgHierarchy

        self.stdout.write('🗑   Flushing old data...')
        from apps.chat_assistant.models import ChatLog
        FeedbackAnswer.objects.all().delete()
        FeedbackResponse.objects.all().delete()
        AggregatedResult.objects.all().delete()
        ReviewerTask.objects.all().delete()
        PeerNomination.objects.all().delete()
        CycleParticipant.objects.all().delete()
        ReviewCycle.objects.all().delete()
        TemplateQuestion.objects.all().delete()
        TemplateSection.objects.all().delete()
        Template.objects.all().delete()
        OrgHierarchy.objects.all().delete()
        # Delete chat logs first (restricted FK), then non-admin users
        ChatLog.objects.exclude(user__email='admin@gamyam.com').delete()
        User.objects.exclude(email='admin@gamyam.com').delete()
        self.stdout.write('    ✓ Cleared')

    # ── Users & Departments ────────────────────────────────────────────────

    def _seed_users(self):
        from apps.users.models import Department, OrgHierarchy

        self.stdout.write('\n👥  Seeding users...')
        dept_map = {}
        for name in ['HR', 'Engineering', 'Product', 'Design']:
            d, _ = Department.objects.get_or_create(name=name)
            dept_map[name] = d

        user_map = {}
        for u in USERS:
            dept = dept_map.get(u['dept'])
            obj, created = User.objects.get_or_create(
                email=u['email'],
                defaults={
                    'first_name':   u['first'],
                    'last_name':    u['last'],
                    'role':         u['role'],
                    'status':       'ACTIVE',
                    'job_title':    u['title'],
                    'department':   dept,
                    'is_staff':     u['role'] in ('SUPER_ADMIN', 'HR_ADMIN'),
                    'is_superuser': u['role'] == 'SUPER_ADMIN',
                },
            )
            obj.first_name = u['first']
            obj.last_name  = u['last']
            obj.role       = u['role']
            obj.status     = 'ACTIVE'
            obj.job_title  = u['title']
            obj.department = dept
            obj.is_staff   = u['role'] in ('SUPER_ADMIN', 'HR_ADMIN')
            obj.is_superuser = u['role'] == 'SUPER_ADMIN'
            obj.set_password(PASSWORD)
            obj.save()
            user_map[u['email']] = obj
            mark = 'created' if created else 'updated'
            self.stdout.write(f"    ✓ {mark}: {u['email']} ({u['role']})")

        self.stdout.write('\n🏢  Seeding org hierarchy...')
        for u in USERS:
            mgr_email = u.get('manager')
            if mgr_email:
                OrgHierarchy.objects.update_or_create(
                    employee=user_map[u['email']],
                    defaults={'manager': user_map[mgr_email]},
                )
                self.stdout.write(f"    ✓ {u['email']} → {mgr_email}")

        return user_map

    # ── Templates ─────────────────────────────────────────────────────────

    def _seed_templates(self, user_map):
        from apps.review_cycles.models import Template, TemplateSection, TemplateQuestion

        self.stdout.write('\n📋  Seeding templates...')
        hr = user_map['hr@gamyam.com']
        tmpl_map = {}

        for tdata in (TEMPLATE_STANDARD, TEMPLATE_LEADERSHIP):
            tmpl = Template.objects.create(
                name=tdata['name'],
                description=tdata['description'],
                created_by=hr,
                is_active=True,
            )
            questions = {}
            q_list = []
            for i, sec_data in enumerate(tdata['sections'], 1):
                sec = TemplateSection.objects.create(
                    template=tmpl, title=sec_data['title'], display_order=i,
                )
                for j, q in enumerate(sec_data['questions'], 1):
                    tq = TemplateQuestion.objects.create(
                        section=sec,
                        question_text=q['text'],
                        type=q['type'],
                        rating_scale_min=1 if q['type'] == 'RATING' else None,
                        rating_scale_max=5 if q['type'] == 'RATING' else None,
                        is_required=True,
                        display_order=j,
                    )
                    q_list.append(tq)
            tmpl_map[tdata['name']] = {'tmpl': tmpl, 'questions': q_list}
            self.stdout.write(f"    ✓ {tdata['name']} ({len(q_list)} questions)")

        return tmpl_map

    # ── Cycles ─────────────────────────────────────────────────────────────

    def _seed_cycles(self, user_map, tmpl_map):
        self.stdout.write('\n🔄  Seeding cycles...')

        now = timezone.now()
        std = tmpl_map['Standard 360° Review']
        ldr = tmpl_map['Leadership & Growth Review']
        hr  = user_map['hr@gamyam.com']

        # Employees who participate in reviews (managers + employees, not HR/admin)
        participants = [
            user_map['manager1@gamyam.com'],
            user_map['manager2@gamyam.com'],
            user_map['manager3@gamyam.com'],
            user_map['emp1@gamyam.com'],
            user_map['emp2@gamyam.com'],
            user_map['emp3@gamyam.com'],
            user_map['emp4@gamyam.com'],
        ]

        # ── 1. ARCHIVED ────────────────────────────────────────────────────
        self._make_cycle(
            name='Q3 2025 Annual Review',
            description='Annual performance review for Q3 2025.',
            template=std['tmpl'], questions=std['questions'],
            state='ARCHIVED', quarter='Q3', year=2025,
            nom_dl=now - timedelta(days=180),
            rev_dl=now - timedelta(days=150),
            created_by=hr,
            participants=participants,
            user_map=user_map,
            submit_fraction=1.0,
            release=True,
            released_offset=-140,
        )

        # ── 2. RESULTS_RELEASED ────────────────────────────────────────────
        self._make_cycle(
            name='Q4 2025 Performance Review',
            description='Q4 2025 end-of-year performance review. Results have been released.',
            template=std['tmpl'], questions=std['questions'],
            state='RESULTS_RELEASED', quarter='Q4', year=2025,
            nom_dl=now - timedelta(days=90),
            rev_dl=now - timedelta(days=60),
            created_by=hr,
            participants=participants,
            user_map=user_map,
            submit_fraction=1.0,
            release=True,
            released_offset=-50,
        )

        # ── 3. CLOSED ──────────────────────────────────────────────────────
        self._make_cycle(
            name='Q1 2026 Mid-Year Check-in',
            description='Mid-year check-in cycle for Q1 2026. Feedback collection complete.',
            template=ldr['tmpl'], questions=ldr['questions'],
            state='CLOSED', quarter='Q1', year=2026,
            nom_dl=now - timedelta(days=45),
            rev_dl=now - timedelta(days=15),
            created_by=hr,
            participants=participants,
            user_map=user_map,
            submit_fraction=1.0,
            release=False,
        )

        # ── 4. ACTIVE (partial submissions) ────────────────────────────────
        self._make_cycle(
            name='Q2 2026 Performance Review',
            description='Q2 2026 performance review — currently collecting feedback.',
            template=std['tmpl'], questions=std['questions'],
            state='ACTIVE', quarter='Q2', year=2026,
            nom_dl=now - timedelta(days=20),
            rev_dl=now + timedelta(days=14),
            created_by=hr,
            participants=participants,
            user_map=user_map,
            submit_fraction=0.5,  # half submitted
            release=False,
        )

        # ── 5. NOMINATION ──────────────────────────────────────────────────
        self._make_nomination_cycle(
            name='Q3 2026 Peer Nominations',
            description='Peer nomination round for Q3 2026. Employees select their reviewers.',
            template=std['tmpl'],
            state='NOMINATION', quarter='Q3', year=2026,
            nom_dl=now + timedelta(days=10),
            rev_dl=now + timedelta(days=35),
            created_by=hr,
            participants=participants,
            user_map=user_map,
        )

        # ── 6. FINALIZED (nominations approved, tasks ready) ───────────────
        self._make_cycle(
            name='Q4 2026 Leadership Assessment',
            description='Leadership and growth assessment — nominations approved, review in progress.',
            template=ldr['tmpl'], questions=ldr['questions'],
            state='FINALIZED', quarter='Q4', year=2026,
            nom_dl=now - timedelta(days=5),
            rev_dl=now + timedelta(days=25),
            created_by=hr,
            participants=participants,
            user_map=user_map,
            submit_fraction=0.0,  # tasks exist but none submitted
            release=False,
        )

        # ── 7. DRAFT ───────────────────────────────────────────────────────
        from apps.review_cycles.models import ReviewCycle
        ReviewCycle.objects.bulk_create([ReviewCycle(
            name='FY2026 Company-Wide Review',
            description='Full company annual review for FY2026. Currently in planning.',
            template=std['tmpl'],
            state='DRAFT',
            quarter='Q4', quarter_year=2026,
            peer_enabled=True,
            peer_min_count=2, peer_max_count=5,
            peer_threshold=3,
            peer_anonymity='ANONYMOUS',
            manager_anonymity='TRANSPARENT',
            nomination_deadline=now + timedelta(days=30),
            review_deadline=now + timedelta(days=60),
            nomination_approval_mode='MANUAL',
            created_by=hr,
        )])
        self.stdout.write('    ✓ FY2026 Company-Wide Review  [DRAFT]')

    # ── Cycle builder ──────────────────────────────────────────────────────

    def _make_cycle(self, name, description, template, questions, state, quarter, year,
                    nom_dl, rev_dl, created_by, participants, user_map,
                    submit_fraction, release, released_offset=None):
        from apps.review_cycles.models import ReviewCycle, CycleParticipant
        from apps.reviewer_workflow.models import ReviewerTask, PeerNomination
        from apps.feedback.models import FeedbackResponse, FeedbackAnswer, AggregatedResult

        now = timezone.now()

        cycle = ReviewCycle(
            name=name, description=description,
            template=template,
            state=state,
            quarter=quarter, quarter_year=year,
            peer_enabled=True,
            peer_min_count=2, peer_max_count=4,
            peer_threshold=3,
            peer_anonymity='ANONYMOUS',
            manager_anonymity='TRANSPARENT',
            nomination_deadline=nom_dl,
            review_deadline=rev_dl,
            nomination_approval_mode='AUTO',
            created_by=created_by,
            results_released_at=now + timedelta(days=released_offset) if release and released_offset else None,
        )
        # Use bulk_create to bypass the custom save() state-transition validation
        ReviewCycle.objects.bulk_create([cycle])

        # Add all participants
        for u in participants:
            CycleParticipant.objects.create(cycle=cycle, user=u)

        # Determine who reviews whom (self + manager + peers from same dept)
        tasks = []
        for reviewee in participants:
            # SELF
            tasks.append(ReviewerTask(
                cycle=cycle, reviewee=reviewee, reviewer=reviewee,
                reviewer_type='SELF',
                anonymity_mode='TRANSPARENT',
                status='CREATED',
            ))
            # MANAGER
            mgr = self._get_manager(reviewee, user_map)
            if mgr and mgr in participants:
                tasks.append(ReviewerTask(
                    cycle=cycle, reviewee=reviewee, reviewer=mgr,
                    reviewer_type='MANAGER',
                    anonymity_mode='TRANSPARENT',
                    status='CREATED',
                ))
            # PEERS (others in same dept, up to 2)
            peers = [p for p in participants
                     if p != reviewee
                     and p.department_id == reviewee.department_id
                     and p != mgr][:2]
            for peer in peers:
                tasks.append(ReviewerTask(
                    cycle=cycle, reviewee=reviewee, reviewer=peer,
                    reviewer_type='PEER',
                    anonymity_mode='ANONYMOUS',
                    status='CREATED',
                ))

        # Remove duplicates by (reviewee, reviewer)
        seen = set()
        unique_tasks = []
        for t in tasks:
            key = (t.reviewee_id, t.reviewer_id)
            if key not in seen:
                seen.add(key)
                unique_tasks.append(t)

        created_tasks = ReviewerTask.objects.bulk_create(unique_tasks)

        # Submit some/all feedback
        total = len(created_tasks)
        n_submit = int(total * submit_fraction)
        random.seed(42)
        to_submit = random.sample(created_tasks, n_submit) if n_submit < total else created_tasks

        for task in to_submit:
            task.status = 'SUBMITTED'
            task.save(update_fields=['status'])

            resp = FeedbackResponse.objects.create(
                task=task,
                submitted_by=task.reviewer,
            )
            answers = self._build_answers(task.reviewer_type, questions)
            FeedbackAnswer.objects.bulk_create([
                FeedbackAnswer(response=resp, question=q, rating_value=rv, text_value=tv)
                for q, rv, tv in answers
            ])

        # Aggregated results for closed/released/archived cycles
        if submit_fraction == 1.0 and state in ('RESULTS_RELEASED', 'CLOSED', 'ARCHIVED'):
            for reviewee in participants:
                rtasks = [t for t in created_tasks if t.reviewee_id == reviewee.id]
                self_score = mgr_score = peer_score = None
                scores = []
                for t in rtasks:
                    resp = FeedbackResponse.objects.filter(task=t).first()
                    if not resp:
                        continue
                    ratings = list(FeedbackAnswer.objects.filter(
                        response=resp, rating_value__isnull=False
                    ).values_list('rating_value', flat=True))
                    if not ratings:
                        continue
                    avg = sum(float(r) for r in ratings) / len(ratings)
                    scores.append(avg)
                    if t.reviewer_type == 'SELF':
                        self_score = Decimal(str(round(avg, 2)))
                    elif t.reviewer_type == 'MANAGER':
                        mgr_score  = Decimal(str(round(avg, 2)))
                    elif t.reviewer_type == 'PEER':
                        peer_score = Decimal(str(round(avg, 2)))

                overall = Decimal(str(round(sum(scores) / len(scores), 2))) if scores else Decimal('0')
                AggregatedResult.objects.update_or_create(
                    cycle=cycle, reviewee=reviewee,
                    defaults={
                        'overall_score': overall,
                        'self_score':    self_score,
                        'manager_score': mgr_score,
                        'peer_score':    peer_score,
                    },
                )

        submitted = len([t for t in created_tasks if t.status == 'SUBMITTED'])
        self.stdout.write(
            f'    ✓ {name}  [{state}]  '
            f'({len(participants)} participants, {len(created_tasks)} tasks, {submitted} submitted)'
        )

    def _make_nomination_cycle(self, name, description, template, state, quarter, year,
                               nom_dl, rev_dl, created_by, participants, user_map):
        """NOMINATION cycle — create participants + some nominations (pending + approved mix)."""
        from apps.review_cycles.models import ReviewCycle, CycleParticipant
        from apps.reviewer_workflow.models import PeerNomination

        cycle = ReviewCycle(
            name=name, description=description,
            template=template,
            state=state,
            quarter=quarter, quarter_year=year,
            peer_enabled=True,
            peer_min_count=2, peer_max_count=4,
            peer_threshold=3,
            peer_anonymity='ANONYMOUS',
            manager_anonymity='TRANSPARENT',
            nomination_deadline=nom_dl,
            review_deadline=rev_dl,
            nomination_approval_mode='MANUAL',
            created_by=created_by,
        )
        ReviewCycle.objects.bulk_create([cycle])
        for u in participants:
            CycleParticipant.objects.create(cycle=cycle, user=u)

        # Create some peer nominations
        noms = []
        for reviewee in participants:
            peers = [p for p in participants if p != reviewee]
            # Each person nominates 2 peers
            for peer in peers[:2]:
                status = 'APPROVED' if hash(f"{reviewee.email}{peer.email}") % 2 == 0 else 'PENDING'
                noms.append(PeerNomination(
                    cycle=cycle,
                    reviewee=reviewee,
                    peer=peer,
                    nominated_by=reviewee,
                    status=status,
                    approved_by=created_by if status == 'APPROVED' else None,
                    approved_at=timezone.now() - timedelta(days=2) if status == 'APPROVED' else None,
                ))

        PeerNomination.objects.bulk_create(noms, ignore_conflicts=True)
        approved = sum(1 for n in noms if n.status == 'APPROVED')
        pending  = sum(1 for n in noms if n.status == 'PENDING')
        self.stdout.write(
            f'    ✓ {name}  [{state}]  '
            f'({len(participants)} participants, {len(noms)} nominations: {approved} approved / {pending} pending)'
        )

    # ── Helpers ────────────────────────────────────────────────────────────

    def _get_manager(self, user, user_map):
        """Return manager user object for given user, or None."""
        for u in USERS:
            if u['email'] == user.email:
                mgr_email = u.get('manager')
                return user_map.get(mgr_email) if mgr_email else None
        return None

    def _build_answers(self, reviewer_type, questions):
        """Return list of (question, rating_value, text_value) tuples."""
        data = ANSWERS.get(reviewer_type, ANSWERS['PEER'])
        ratings = data['ratings']
        texts   = data['texts']
        result  = []
        r_idx = t_idx = 0
        for q in questions:
            if q.type == 'RATING':
                val = Decimal(str(ratings[r_idx % len(ratings)]))
                result.append((q, val, None))
                r_idx += 1
            else:
                result.append((q, None, texts[t_idx % len(texts)]))
                t_idx += 1
        return result
