"""
Seed users and org hierarchy from Gamyam People export (JSON in .md file).

Reads a JSON array where each object has:
  - id, email, first_name, last_name, middle_name
  - basic_employment.current_transition.title → job_title
  - basic_employment.current_transition.basic_department.name → department
  - basic_employment.reporting_to_id → manager (UUID; resolved via id→email map)

All users are created with role=EMPLOYEE; status=ACTIVE; password=Admin@123 (change after first login).
Existing emails are skipped.
Org hierarchy is created only when the manager (reporting_to_id) is also present in
the same file; if the export is a subset, unresolved manager links are skipped.

Usage:
  python manage.py seed_gamyam_people
  python manage.py seed_gamyam_people --file /path/to/Gamyam People.md
  python manage.py seed_gamyam_people --dry-run
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth import get_user_model

User = get_user_model()


def load_gamyam_json(path):
    """Load JSON from .md file (handles \\[ \\] and \\_ escaping; other \\ escaped for JSON)."""
    raw = path.read_text(encoding='utf-8').strip()
    raw = raw.replace(r'\[', '[').replace(r'\]', ']').replace(r'\_', '_')
    # Escape remaining backslashes so JSON doesn't treat e.g. "GIT \- 017" as invalid
    raw = raw.replace('\\', '\\\\')
    return json.loads(raw)


def get(obj, *keys, default=None):
    """Nested get: get({'a': {'b': 1}}, 'a', 'b') -> 1."""
    for k in keys:
        if obj is None or not isinstance(obj, dict):
            return default
        obj = obj.get(k)
    return obj


class Command(BaseCommand):
    help = 'Seed users and org hierarchy from Gamyam People export (JSON)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            default=None,
            help='Path to Gamyam People.md (default: project root / Gamyam People.md)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Parse file and report what would be done without writing to DB',
        )

    def handle(self, *args, **options):
        from apps.users.models import Department, OrgHierarchy

        file_path = options.get('file')
        if file_path:
            path = Path(file_path)
        else:
            # Project root: .../backend/apps/users/management/commands/ -> 6 parents -> 360_Django
            base = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
            path = base / 'Gamyam People.md'
        if not path.exists():
            self.stdout.write(self.style.ERROR(f'File not found: {path}'))
            return

        self.stdout.write(f'Loading: {path}')
        try:
            data = load_gamyam_json(path)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Failed to parse JSON: {e}'))
            return

        if not isinstance(data, list):
            self.stdout.write(self.style.ERROR('Expected JSON array'))
            return

        # Build basic_employment.id → email for manager resolution
        # (reporting_to_id references basic_employment.id, NOT top-level id)
        id_to_email = {}
        for item in data:
            emp_id = get(item, 'basic_employment', 'id')
            email = (get(item, 'email') or '').strip().lower()
            if emp_id and email:
                id_to_email[str(emp_id).strip()] = email

        # Collect unique department names
        dept_names = set()
        for item in data:
            name = get(item, 'basic_employment', 'current_transition', 'basic_department', 'name')
            if name and str(name).strip():
                dept_names.add(str(name).strip())

        if options.get('dry_run'):
            self.stdout.write(self.style.SUCCESS(f'[DRY RUN] Would process {len(data)} people, {len(dept_names)} departments'))
            return

        with transaction.atomic():
            # 1) Departments
            self.stdout.write('Seeding departments...')
            dept_by_name = {}
            for name in sorted(dept_names):
                dept, created = Department.objects.get_or_create(name=name)
                dept_by_name[name] = dept
                self.stdout.write(f'  {"✓ created" if created else "✓ exists"}: {name}')

            # 2) Users (role=EMPLOYEE, skip existing email)
            created_users = 0
            skipped_users = 0
            self.stdout.write('Seeding users...')
            for item in data:
                email = (get(item, 'email') or '').strip().lower()
                if not email:
                    continue
                if User.objects.filter(email=email).exists():
                    skipped_users += 1
                    continue
                first_name = (get(item, 'first_name') or '').strip() or ''
                last_name = (get(item, 'last_name') or '').strip() or ''
                middle_name = get(item, 'middle_name')
                middle_name = (middle_name and str(middle_name).strip()) or None
                title = get(item, 'basic_employment', 'current_transition', 'title')
                job_title = (title and str(title).strip()) or None
                dept_name = get(item, 'basic_employment', 'current_transition', 'basic_department', 'name')
                department = dept_by_name.get((dept_name or '').strip()) if dept_name else None

                user = User(
                    email=email,
                    first_name=first_name,
                    middle_name=middle_name,
                    last_name=last_name,
                    job_title=job_title,
                    role='EMPLOYEE',
                    status='ACTIVE',
                    department=department,
                )
                user.set_password('Admin@123')
                user.save()
                created_users += 1
            self.stdout.write(f'  Created: {created_users}, Skipped (existing): {skipped_users}')

            # 3) Org hierarchy (employee → manager); only when manager is also in this file
            self.stdout.write('Seeding org hierarchy...')
            hierarchy_created = 0
            hierarchy_skipped = 0
            for item in data:
                email = (get(item, 'email') or '').strip().lower()
                if not email:
                    continue
                try:
                    employee = User.objects.get(email=email)
                except User.DoesNotExist:
                    hierarchy_skipped += 1
                    continue
                reporting_to_id = get(item, 'basic_employment', 'reporting_to_id')
                if not reporting_to_id:
                    continue
                reporting_to_id = str(reporting_to_id).strip()
                manager_email = id_to_email.get(reporting_to_id)
                if not manager_email or manager_email == email:
                    continue  # manager not in this export or self
                try:
                    manager = User.objects.get(email=manager_email)
                except User.DoesNotExist:
                    hierarchy_skipped += 1
                    continue
                _, created = OrgHierarchy.objects.update_or_create(
                    employee=employee,
                    defaults={'manager': manager},
                )
                if created:
                    hierarchy_created += 1
            self.stdout.write(f'  Created: {hierarchy_created}, Skipped: {hierarchy_skipped} (hierarchy only when manager is in same file)')

        self.stdout.write(self.style.SUCCESS('\n✅ Gamyam people seed completed.'))
