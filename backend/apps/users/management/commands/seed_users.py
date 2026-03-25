"""
Management command: seed_users
Seeds demo users, departments, org hierarchy, and one template:
  - Simple 360° Review (short, easy questions for self/manager/peer)
Common password for all seeded users: Admin@123
Usage: python manage.py seed_users
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth import get_user_model

User = get_user_model()

SEED_PASSWORD = 'Admin@123'

USERS = [
    # Only the system super-admin account is seeded — all real employees are imported via CSV
    {'email': 'admin@gamyam.com', 'first_name': 'Super', 'last_name': 'Admin', 'role': 'SUPER_ADMIN', 'job_title': 'System Administrator', 'department': None},
]

ORG_HIERARCHY = []

# Single template: easy questions for self, manager, and peer
TEMPLATE_SIMPLE = {
    'name': 'Simple 360° Review',
    'description': 'Short, easy questions for self, manager, and peer feedback.',
    'sections': [
        {
            'title': 'Feedback',
            'questions': [
                {'text': "Is this person's work good?", 'type': 'RATING'},
                {'text': 'Does this person communicate clearly and listen well?', 'type': 'RATING'},
                {'text': 'Is this person good to work with?', 'type': 'RATING'},
                {'text': 'What does this person do well? (one thing)', 'type': 'TEXT'},
                {'text': 'What can this person do better? (one thing)', 'type': 'TEXT'},
            ],
        },
    ],
}


class Command(BaseCommand):
    help = 'Seed demo users, departments, org hierarchy, and the Standard 360° Review template'

    def handle(self, *args, **options):
        with transaction.atomic():
            self._seed_departments()
            self._seed_users()
            self._seed_org_hierarchy()
            self._seed_template()

        self.stdout.write(self.style.SUCCESS('\n✅  Seed completed! Password for all: ' + SEED_PASSWORD))

    # ── Departments ───────────────────────────────────────────────────────────

    def _seed_departments(self):
        from apps.users.models import Department

        dept_names = {u['department'] for u in USERS if u['department']}
        self.stdout.write('Seeding departments...')
        for name in sorted(dept_names):
            dept, created = Department.objects.get_or_create(name=name)
            mark = '✓ created' if created else '✓ exists '
            self.stdout.write(f'  {mark}: {name}')

    # ── Users ─────────────────────────────────────────────────────────────────

    def _seed_users(self):
        from apps.users.models import Department

        self.stdout.write('\nSeeding users...')
        for u in USERS:
            dept = Department.objects.get(name=u['department']) if u['department'] else None

            user, created = User.objects.get_or_create(
                email=u['email'],
                defaults={
                    'first_name': u['first_name'],
                    'last_name':  u['last_name'],
                    'role':       u['role'],
                    'status':     'ACTIVE',
                    'job_title':  u['job_title'],
                    'department': dept,
                    'is_staff':   u['role'] == 'SUPER_ADMIN',
                    'is_superuser': u['role'] == 'SUPER_ADMIN',
                },
            )

            # Always refresh password and profile fields on re-run
            user.set_password(SEED_PASSWORD)
            user.first_name  = u['first_name']
            user.last_name   = u['last_name']
            user.role        = u['role']
            user.status      = 'ACTIVE'
            user.job_title   = u['job_title']
            user.department  = dept
            user.is_staff    = u['role'] == 'SUPER_ADMIN'
            user.is_superuser = u['role'] == 'SUPER_ADMIN'
            user.save()

            mark = '✓ created' if created else '✓ updated'
            self.stdout.write(f'  {mark}: {u["email"]} ({u["role"]})')

    # ── Org Hierarchy ─────────────────────────────────────────────────────────

    def _seed_org_hierarchy(self):
        from apps.users.models import OrgHierarchy

        self.stdout.write('\nSeeding org hierarchy...')
        for emp_email, mgr_email in ORG_HIERARCHY:
            try:
                employee = User.objects.get(email=emp_email)
            except User.DoesNotExist:
                self.stdout.write(self.style.WARNING(f'  ⚠ Skipped (user not found): {emp_email}'))
                continue

            if mgr_email is None:
                # No manager — remove any existing hierarchy entry
                OrgHierarchy.objects.filter(employee=employee).delete()
                self.stdout.write(f'  ✓ {emp_email} → (no manager)')
                continue

            try:
                manager = User.objects.get(email=mgr_email)
            except User.DoesNotExist:
                self.stdout.write(self.style.WARNING(f'  ⚠ Manager not found for {emp_email}: {mgr_email}'))
                continue

            OrgHierarchy.objects.update_or_create(
                employee=employee,
                defaults={'manager': manager},
            )
            self.stdout.write(f'  ✓ {emp_email} → {mgr_email}')

    # ── Template ──────────────────────────────────────────────────────────────

    def _seed_template(self):
        from apps.review_cycles.models import Template, TemplateSection, TemplateQuestion

        self.stdout.write('\nSeeding templates...')
        hr_user = User.objects.filter(email='admin@gamyam.com').first()

        for template_data in (TEMPLATE_SIMPLE,):  # only one template: Simple 360° Review
            template, created = Template.objects.get_or_create(
                name=template_data['name'],
                defaults={
                    'description': template_data['description'],
                    'created_by':  hr_user,
                },
            )

            if not created:
                self.stdout.write(f'  ✓ Template already exists: {template.name} (ID: {template.id})')
                continue

            self.stdout.write(f'  ✓ Template created: {template.name} (ID: {template.id})')

            for i, section_data in enumerate(template_data['sections'], start=1):
                section = TemplateSection.objects.create(
                    template=template,
                    title=section_data['title'],
                    display_order=i,
                )
                for j, q in enumerate(section_data['questions'], start=1):
                    TemplateQuestion.objects.create(
                        section=section,
                        question_text=q['text'],
                        type=q['type'],
                        rating_scale_min=1 if q['type'] == 'RATING' else None,
                        rating_scale_max=5 if q['type'] == 'RATING' else None,
                        display_order=j,
                    )

        self.stdout.write('  ✓ Templates and questions created')
