import uuid
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('role', 'SUPER_ADMIN')
        extra_fields.setdefault('status', 'ACTIVE')
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)


class Department(models.Model):
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name       = models.CharField(max_length=150, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'departments'
        ordering = ['name']

    def __str__(self):
        return self.name


class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [
        ('SUPER_ADMIN', 'Super Admin'),
        ('HR_ADMIN',    'HR Admin'),
        ('MANAGER',     'Manager'),
        ('EMPLOYEE',    'Employee'),
    ]
    STATUS_CHOICES = [
        ('ACTIVE',     'Active'),
        ('INACTIVE',   'Inactive'),
        ('SUSPENDED',  'Suspended'),
    ]

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email       = models.EmailField(unique=True)
    first_name  = models.CharField(max_length=100, blank=True)
    middle_name = models.CharField(max_length=100, blank=True, null=True)
    last_name   = models.CharField(max_length=100, blank=True)
    job_title   = models.CharField(max_length=150, blank=True, null=True)
    role        = models.CharField(max_length=20, choices=ROLE_CHOICES, default='EMPLOYEE')
    status      = models.CharField(max_length=10, choices=STATUS_CHOICES, default='ACTIVE')
    avatar_url  = models.URLField(blank=True, null=True)
    department  = models.ForeignKey(Department, null=True, blank=True, on_delete=models.SET_NULL, related_name='members')
    is_staff    = models.BooleanField(default=False)
    last_login_at = models.DateTimeField(null=True, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    USERNAME_FIELD  = 'email'
    REQUIRED_FIELDS = []
    objects = UserManager()

    class Meta:
        db_table = 'users'
        ordering = ['email']

    def __str__(self):
        return f'{self.get_full_name()} <{self.email}>'

    def get_full_name(self):
        parts = [self.first_name, self.middle_name, self.last_name]
        return ' '.join(p for p in parts if p).strip() or self.email


class OrgHierarchy(models.Model):
    employee   = models.OneToOneField(User, on_delete=models.CASCADE, related_name='manager_relation')
    manager    = models.ForeignKey(User, on_delete=models.CASCADE, related_name='direct_reports')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'org_hierarchy'

    def __str__(self):
        return f'{self.employee} → {self.manager}'
