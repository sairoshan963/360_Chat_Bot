import csv
import io

from django.db.models import Q
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from shared.permissions import IsSuperAdmin, IsHRAdmin
from .models import Department, OrgHierarchy
from .serializers import (
    UserSerializer,
    CreateUserSerializer,
    UpdateUserSerializer,
    DepartmentSerializer,
)

User = get_user_model()


# ─── Users ────────────────────────────────────────────────────────────────────

class UserListCreateView(APIView):
    # GET is open to HR_ADMIN (needs to pick participants for cycles)
    # POST (create user) remains SUPER_ADMIN only — enforced inside post()
    permission_classes = [IsAuthenticated, IsHRAdmin]

    def get(self, request):
        qs = User.objects.select_related('department', 'manager_relation__manager').all()

        # Filters
        role   = request.query_params.get('role')
        user_status = request.query_params.get('status')  # Renamed to avoid shadowing
        dept   = request.query_params.get('department')
        search = request.query_params.get('search')

        if role:
            qs = qs.filter(role=role)
        if user_status:
            qs = qs.filter(status=user_status)
        if dept:
            qs = qs.filter(department__id=dept)
        if search:
            qs = qs.filter(
                Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(middle_name__icontains=search)
                | Q(last_name__icontains=search)
            )
        qs = qs.order_by('first_name', 'last_name', 'email')
        return Response({'success': True, 'users': UserSerializer(qs, many=True).data})

    def post(self, request):
        if request.user.role != 'SUPER_ADMIN':
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Only Super Admin can create users.')
        serializer = CreateUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        from apps.audit.models import AuditLog
        AuditLog.log(
            actor=request.user, action='USER_CREATED',
            entity_type='user', entity_id=user.id,
            new_value={'email': user.email, 'role': user.role},
        )
        return Response({'success': True, 'user': UserSerializer(user).data}, status=201)


class UserDetailView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def _get_user(self, pk):
        try:
            return User.objects.select_related('department', 'manager_relation__manager').get(id=pk)
        except User.DoesNotExist:
            return None

    def get(self, request, pk):
        user = self._get_user(pk)
        if not user:
            return Response({'success': False, 'error': 'User not found'}, status=404)
        return Response({'success': True, 'user': UserSerializer(user).data})

    def patch(self, request, pk):
        user = self._get_user(pk)
        if not user:
            return Response({'success': False, 'error': 'User not found'}, status=404)
        serializer = UpdateUserSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        from apps.audit.models import AuditLog
        AuditLog.log(
            actor=request.user, action='USER_UPDATED',
            entity_type='user', entity_id=user.id,
            new_value={k: request.data[k] for k in request.data},
        )
        return Response({'success': True, 'user': UserSerializer(updated).data})

    def delete(self, request, pk):
        user = self._get_user(pk)
        if not user:
            return Response({'success': False, 'error': 'User not found'}, status=404)
        if user == request.user:
            return Response({'success': False, 'error': 'Cannot deactivate your own account'}, status=400)
        user.status = 'INACTIVE'
        user.save(update_fields=['status'])
        from apps.audit.models import AuditLog
        AuditLog.log(
            actor=request.user, action='USER_DEACTIVATED',
            entity_type='user', entity_id=user.id,
            new_value={'email': user.email, 'status': 'INACTIVE'},
        )
        return Response({'success': True, 'message': 'User deactivated'})


# ─── Admin: Reset a specific user's password ─────────────────────────────────

class AdminResetUserPasswordView(APIView):
    """
    POST /api/v1/users/<pk>/reset-password/
    Super Admin triggers a password reset email for any user.
    """
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def post(self, request, pk):
        try:
            target_user = User.objects.get(id=pk)
        except User.DoesNotExist:
            return Response({'success': False, 'error': 'User not found'}, status=404)

        if target_user.status != 'ACTIVE':
            return Response({'success': False, 'error': 'Cannot reset password for inactive user'}, status=400)

        from apps.auth_app.services import _create_reset_token
        from shared.email import send_admin_password_reset
        from django.conf import settings

        raw_token  = _create_reset_token(target_user)
        reset_link = f'{settings.FRONTEND_URL}/reset-password?token={raw_token}'
        send_admin_password_reset(
            to_email   = target_user.email,
            first_name = target_user.first_name,
            reset_link = reset_link,
            admin_name = request.user.get_full_name() or request.user.email,
        )

        from apps.audit.models import AuditLog
        AuditLog.log(
            actor=request.user, action='ADMIN_PASSWORD_RESET',
            entity_type='user', entity_id=target_user.id,
            new_value={'target_user': target_user.get_full_name(), 'email': target_user.email},
        )

        return Response({'success': True, 'message': f'Password reset email sent to {target_user.email}'})


# ─── CSV Bulk Import ──────────────────────────────────────────────────────────

class UserBulkImportView(APIView):
    """
    POST /api/v1/users/import/
    Columns: email, first_name, middle_name, last_name, job_title, role, department, manager_email
    - department: auto-creates if not exists
    - manager_email: assigns OrgHierarchy after all users are created (2-pass)
    """
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def post(self, request):
        file = request.FILES.get('file')
        if not file:
            return Response({'success': False, 'error': 'No file uploaded'}, status=400)
        
        # Validate file size (max 10MB)
        if file.size > 10 * 1024 * 1024:
            return Response({'success': False, 'error': 'File must be smaller than 10MB'}, status=400)
        
        # Validate file type
        if not file.name.lower().endswith('.csv'):
            return Response({'success': False, 'error': 'Only CSV files are allowed'}, status=400)

        try:
            content = file.read().decode('utf-8-sig')  # handle BOM from Excel exports
        except UnicodeDecodeError:
            return Response({'success': False, 'error': 'Invalid CSV file encoding'}, status=400)
            
        reader  = csv.DictReader(io.StringIO(content))
        created = 0
        skipped = 0
        updated = 0
        errors  = []
        manager_assignments = []  # defer until after all users created
        row_count = 0

        for i, row in enumerate(reader, start=2):
            row_count += 1
            # Limit number of rows to prevent resource exhaustion
            if row_count > 1000:
                errors.append({'row': i, 'error': 'Maximum 1000 rows allowed per import'})
                break
            email = (row.get('email') or '').strip().lower()
            if not email:
                errors.append({'row': i, 'error': 'email is required'})
                continue

            # Department — auto-create
            dept_name = (row.get('department') or '').strip()
            dept = None
            if dept_name:
                dept, _ = Department.objects.get_or_create(name=dept_name)

            role = (row.get('role') or 'EMPLOYEE').strip().upper()
            if role not in ['SUPER_ADMIN', 'HR_ADMIN', 'MANAGER', 'EMPLOYEE']:
                role = 'EMPLOYEE'

            manager_email = (row.get('manager_email') or '').strip().lower()

            try:
                existing = User.objects.get(email=email)
            except User.DoesNotExist:
                existing = None

            if existing is not None:
                changed = False
                if dept and not existing.department_id:
                    existing.department = dept
                    changed = True
                if role and existing.role != role:
                    existing.role = role
                    changed = True
                if changed:
                    existing.save()
                    updated += 1
                else:
                    skipped += 1
                if manager_email:
                    manager_assignments.append((email, manager_email))
                continue

            user = User(
                email=email,
                first_name=(row.get('first_name') or '').strip(),
                middle_name=(row.get('middle_name') or '').strip() or None,
                last_name=(row.get('last_name') or '').strip(),
                job_title=(row.get('job_title') or '').strip() or None,
                role=role,
                status='ACTIVE',
                department=dept,
            )
            user.set_unusable_password()
            user.save()
            created += 1

            if manager_email:
                manager_assignments.append((email, manager_email))

        # ── 2nd pass: assign managers (all users now exist) ──────────────
        manager_linked = 0
        manager_errors = []
        for emp_email, mgr_email in manager_assignments:
            try:
                emp = User.objects.get(email=emp_email)
                mgr = User.objects.get(email=mgr_email)
                OrgHierarchy.objects.update_or_create(
                    employee=emp, defaults={'manager': mgr}
                )
                manager_linked += 1
            except User.DoesNotExist:
                manager_errors.append(f'{emp_email} → manager {mgr_email} not found')

        from apps.audit.models import AuditLog
        AuditLog.log(
            actor=request.user, action='IMPORT_ORG',
            entity_type='bulk_import',
            new_value={'created': created, 'updated': updated, 'skipped': skipped, 'manager_linked': manager_linked},
        )

        return Response({
            'success':        True,
            'created':        created,
            'updated':        updated,
            'skipped':        skipped,
            'manager_linked': manager_linked,
            'errors':         errors + [{'row': '—', 'error': e} for e in manager_errors],
        })


# ─── Departments ──────────────────────────────────────────────────────────────

class DepartmentListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        depts = Department.objects.all()
        return Response({'success': True, 'departments': DepartmentSerializer(depts, many=True).data})

    def post(self, request):
        serializer = DepartmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dept = serializer.save()
        return Response({'success': True, 'department': DepartmentSerializer(dept).data}, status=201)


class DepartmentDetailView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def patch(self, request, pk):
        try:
            dept = Department.objects.get(id=pk)
        except Department.DoesNotExist:
            return Response({'success': False, 'error': 'Department not found'}, status=404)
        serializer = DepartmentSerializer(dept, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({'success': True, 'department': serializer.data})

    def delete(self, request, pk):
        try:
            dept = Department.objects.get(id=pk)
        except Department.DoesNotExist:
            return Response({'success': False, 'error': 'Department not found'}, status=404)
        dept.delete()
        return Response({'success': True, 'message': 'Department deleted'})


# ─── Org Hierarchy ────────────────────────────────────────────────────────────

class OrgHierarchyView(APIView):
    """Returns org hierarchy filtered by the requesting user's role."""
    permission_classes = [IsAuthenticated]

    def _subtree_ids(self, root_id, all_users_by_manager):
        """Recursively collect IDs of root and all descendants."""
        ids = {root_id}
        queue = [root_id]
        while queue:
            current = queue.pop()
            for child_id in all_users_by_manager.get(current, []):
                if child_id not in ids:
                    ids.add(child_id)
                    queue.append(child_id)
        return ids

    def get(self, request):
        me = request.user
        all_active = User.objects.select_related('department', 'manager_relation__manager').filter(status='ACTIVE')

        if me.role in ('SUPER_ADMIN', 'HR_ADMIN'):
            users = all_active

        elif me.role == 'MANAGER':
            # Build manager_id -> [child_ids] map
            children_of = {}
            for u in all_active:
                try:
                    mgr_id = u.manager_relation.manager_id
                    children_of.setdefault(mgr_id, []).append(u.id)
                except OrgHierarchy.DoesNotExist:
                    pass
            subtree = self._subtree_ids(me.id, children_of)
            users = all_active.filter(id__in=subtree)

        else:  # EMPLOYEE
            ids = {me.id}
            try:
                ids.add(me.manager_relation.manager_id)
            except OrgHierarchy.DoesNotExist:
                pass
            users = all_active.filter(id__in=ids)

        data = []
        for u in users:
            try:
                manager_id = str(u.manager_relation.manager.id)
            except OrgHierarchy.DoesNotExist:
                manager_id = None
            data.append({
                'id':          str(u.id),
                'email':       u.email,
                'first_name':  u.first_name,
                'middle_name': u.middle_name,
                'last_name':   u.last_name,
                'job_title':   u.job_title,
                'role':        u.role,
                'status':      u.status,
                'department':  u.department.name if u.department else None,
                'avatar_url':  u.avatar_url,
                'manager_id':  manager_id,
            })
        return Response({'success': True, 'hierarchy': data})

    def post(self, request):
        """Assign or reassign a manager to an employee."""
        employee_id = request.data.get('employee_id')
        manager_id  = request.data.get('manager_id')

        if not employee_id or not manager_id:
            return Response({'success': False, 'error': 'employee_id and manager_id are required'}, status=400)

        try:
            employee = User.objects.get(id=employee_id)
            manager  = User.objects.get(id=manager_id)
        except User.DoesNotExist:
            return Response({'success': False, 'error': 'User not found'}, status=404)

        if employee == manager:
            return Response({'success': False, 'error': 'Employee cannot be their own manager'}, status=400)

        # Check for circular hierarchy
        def would_create_cycle(emp_id, mgr_id):
            """Check if assigning mgr_id as manager of emp_id would create a cycle"""
            visited = set()
            current = mgr_id
            
            while current and current not in visited:
                visited.add(current)
                if current == emp_id:
                    return True
                try:
                    hierarchy = OrgHierarchy.objects.get(employee_id=current)
                    current = hierarchy.manager_id
                except OrgHierarchy.DoesNotExist:
                    break
            return False
        
        if would_create_cycle(str(employee.id), str(manager.id)):
            return Response({'success': False, 'error': 'This assignment would create a circular hierarchy'}, status=400)

        OrgHierarchy.objects.update_or_create(employee=employee, defaults={'manager': manager})
        return Response({'success': True, 'message': f'{employee.get_full_name()} now reports to {manager.get_full_name()}'})
