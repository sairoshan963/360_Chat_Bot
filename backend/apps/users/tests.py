"""
Tests: Users module
Note: User management routes require SUPER_ADMIN role (same as Node.js).
"""
import pytest
from rest_framework.test import APIClient
from apps.users.models import User, Department, OrgHierarchy


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def dept(db):
    return Department.objects.create(name='Engineering')


def _make(email, role, dept, password='Test@1234'):
    return User.objects.create_user(
        email=email, password=password,
        first_name='Test', last_name=role.title(),
        role=role, department=dept,
    )


def _login(client, user):
    resp = client.post('/api/v1/auth/login/', {'email': user.email, 'password': 'Test@1234'}, format='json')
    assert resp.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {resp.data["access"]}')


class TestUserList:
    def test_super_admin_can_list_users(self, client, dept):
        sa = _make('sa@test.com', 'SUPER_ADMIN', dept)
        _login(client, sa)
        resp = client.get('/api/v1/users/')
        assert resp.status_code == 200
        assert 'users' in resp.data

    def test_employee_cannot_list_users(self, client, dept):
        emp = _make('emp@test.com', 'EMPLOYEE', dept)
        _login(client, emp)
        resp = client.get('/api/v1/users/')
        assert resp.status_code == 403

    def test_unauthenticated_rejected(self, client, db):
        resp = client.get('/api/v1/users/')
        assert resp.status_code == 401

    def test_hr_cannot_list_users(self, client, dept):
        hr = _make('hr@test.com', 'HR_ADMIN', dept)
        _login(client, hr)
        resp = client.get('/api/v1/users/')
        assert resp.status_code == 403


class TestCreateUser:
    def test_super_admin_can_create_user(self, client, dept):
        sa = _make('sa2@test.com', 'SUPER_ADMIN', dept)
        _login(client, sa)
        resp = client.post('/api/v1/users/', {
            'email': 'newuser@test.com',
            'first_name': 'New', 'last_name': 'User',
            'role': 'EMPLOYEE', 'department': str(dept.id),
        }, format='json')
        assert resp.status_code == 201
        assert User.objects.filter(email='newuser@test.com').exists()

    def test_duplicate_email_rejected(self, client, dept):
        sa = _make('sa3@test.com', 'SUPER_ADMIN', dept)
        _make('existing@test.com', 'EMPLOYEE', dept)
        _login(client, sa)
        resp = client.post('/api/v1/users/', {
            'email': 'existing@test.com',
            'first_name': 'X', 'last_name': 'Y',
            'role': 'EMPLOYEE', 'department': str(dept.id),
        }, format='json')
        assert resp.status_code == 400


class TestUpdateUser:
    def test_super_admin_can_deactivate_user(self, client, dept):
        sa  = _make('sa4@test.com', 'SUPER_ADMIN', dept)
        emp = _make('emp2@test.com', 'EMPLOYEE', dept)
        _login(client, sa)
        resp = client.delete(f'/api/v1/users/{emp.id}/')
        assert resp.status_code == 200
        emp.refresh_from_db()
        assert emp.status == 'INACTIVE'

    def test_super_admin_can_update_role(self, client, dept):
        sa  = _make('sa5@test.com', 'SUPER_ADMIN', dept)
        emp = _make('emp3@test.com', 'EMPLOYEE', dept)
        _login(client, sa)
        resp = client.patch(f'/api/v1/users/{emp.id}/', {'role': 'MANAGER'}, format='json')
        assert resp.status_code == 200
        emp.refresh_from_db()
        assert emp.role == 'MANAGER'


class TestDepartments:
    def test_super_admin_can_list_departments(self, client, dept):
        sa = _make('sa6@test.com', 'SUPER_ADMIN', dept)
        _login(client, sa)
        resp = client.get('/api/v1/users/departments/')
        assert resp.status_code == 200
        assert len(resp.data['departments']) >= 1

    def test_super_admin_can_create_department(self, client, dept):
        sa = _make('sa7@test.com', 'SUPER_ADMIN', dept)
        _login(client, sa)
        resp = client.post('/api/v1/users/departments/', {'name': 'Marketing'}, format='json')
        assert resp.status_code == 201
        assert Department.objects.filter(name='Marketing').exists()


class TestOrgHierarchy:
    def test_get_hierarchy_returns_flat_list_with_manager_id(self, client, dept):
        sa  = _make('sa8@test.com', 'SUPER_ADMIN', dept)
        mgr = _make('mgr@test.com', 'MANAGER', dept)
        emp = _make('emp4@test.com', 'EMPLOYEE', dept)
        OrgHierarchy.objects.create(employee=emp, manager=mgr)
        _login(client, sa)
        resp = client.get('/api/v1/users/org/hierarchy/')
        assert resp.status_code == 200
        data = resp.json()
        assert data['success'] is True
        assert 'hierarchy' in data
        hierarchy = {str(u['id']): u for u in data['hierarchy']}
        assert str(emp.id) in hierarchy
        assert hierarchy[str(emp.id)]['manager_id'] == str(mgr.id)
        assert str(mgr.id) in hierarchy
        assert hierarchy[str(mgr.id)]['manager_id'] is None

    def test_super_admin_can_set_manager(self, client, dept):
        sa  = _make('sa8@test.com', 'SUPER_ADMIN', dept)
        mgr = _make('mgr@test.com', 'MANAGER', dept)
        emp = _make('emp4@test.com', 'EMPLOYEE', dept)
        _login(client, sa)
        resp = client.post('/api/v1/users/org/hierarchy/', {
            'employee_id': str(emp.id),
            'manager_id':  str(mgr.id),
        }, format='json')
        assert resp.status_code in (200, 201)
        assert OrgHierarchy.objects.filter(employee=emp, manager=mgr).exists()
