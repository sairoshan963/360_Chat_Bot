import csv
import io

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
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        qs = User.objects.select_related('department', 'manager_relation__manager').all()

        # Filters
        role   = request.query_params.get('role')
        status = request.query_params.get('status')
        dept   = request.query_params.get('department')
        search = request.query_params.get('search')

        if role:
            qs = qs.filter(role=role)
        if status:
            qs = qs.filter(status=status)
        if dept:
            qs = qs.filter(department__id=dept)
        if search:
            qs = qs.filter(
                email__icontains=search
            ) | qs.filter(first_name__icontains=search) | qs.filter(last_name__icontains=search)

        return Response({'success': True, 'users': UserSerializer(qs, many=True).data})

    def post(self, request):
        serializer = CreateUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
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
        return Response({'success': True, 'user': UserSerializer(updated).data})

    def delete(self, request, pk):
        user = self._get_user(pk)
        if not user:
            return Response({'success': False, 'error': 'User not found'}, status=404)
        if user == request.user:
            return Response({'success': False, 'error': 'Cannot deactivate your own account'}, status=400)
        user.status = 'INACTIVE'
        user.save(update_fields=['status'])
        return Response({'success': True, 'message': 'User deactivated'})


# ─── CSV Bulk Import ──────────────────────────────────────────────────────────

class UserBulkImportView(APIView):
    """
    POST /api/v1/users/import/
    Accepts CSV with columns: email, first_name, middle_name, last_name, job_title, role, department
    """
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def post(self, request):
        file = request.FILES.get('file')
        if not file:
            return Response({'success': False, 'error': 'No file uploaded'}, status=400)

        content   = file.read().decode('utf-8')
        reader    = csv.DictReader(io.StringIO(content))
        created   = 0
        skipped   = 0
        errors    = []

        for i, row in enumerate(reader, start=2):
            email = (row.get('email') or '').strip().lower()
            if not email:
                errors.append({'row': i, 'error': 'email is required'})
                continue

            if User.objects.filter(email=email).exists():
                skipped += 1
                continue

            dept_name = (row.get('department') or '').strip()
            dept = None
            if dept_name:
                dept, _ = Department.objects.get_or_create(name=dept_name)

            role = (row.get('role') or 'EMPLOYEE').strip().upper()
            if role not in ['SUPER_ADMIN', 'HR_ADMIN', 'MANAGER', 'EMPLOYEE']:
                role = 'EMPLOYEE'

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

        return Response({
            'success': True,
            'created': created,
            'skipped': skipped,
            'errors':  errors,
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
    """Returns all users as a flat list with manager_id for org tree rendering."""
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        users = User.objects.select_related('department', 'manager_relation__manager').filter(status='ACTIVE')
        data = []
        for u in users:
            manager_rel = getattr(u, 'manager_relation', None)
            data.append({
                'id':          str(u.id),
                'email':       u.email,
                'first_name':  u.first_name,
                'middle_name': u.middle_name,
                'last_name':   u.last_name,
                'job_title':   u.job_title,
                'role':       u.role,
                'status':     u.status,
                'department': u.department.name if u.department else None,
                'avatar_url': u.avatar_url,
                'manager_id': str(manager_rel.manager.id) if manager_rel else None,
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

        OrgHierarchy.objects.update_or_create(employee=employee, defaults={'manager': manager})
        return Response({'success': True, 'message': f'{employee.get_full_name()} now reports to {manager.get_full_name()}'})
