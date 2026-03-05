from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Department, OrgHierarchy


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display  = ('email', 'first_name', 'middle_name', 'last_name', 'role', 'status', 'department', 'created_at')
    list_filter   = ('role', 'status', 'department')
    search_fields = ('email', 'first_name', 'middle_name', 'last_name')
    ordering      = ('email',)

    fieldsets = (
        (None,           {'fields': ('email', 'password')}),
        ('Personal Info',{'fields': ('first_name', 'last_name', 'job_title', 'avatar_url', 'department')}),
        ('Permissions',  {'fields': ('role', 'status', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Dates',        {'fields': ('last_login_at', 'created_at', 'updated_at')}),
    )
    readonly_fields = ('last_login_at', 'created_at', 'updated_at')

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'first_name', 'middle_name', 'last_name', 'role', 'status'),
        }),
    )


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display  = ('name', 'created_at')
    search_fields = ('name',)


@admin.register(OrgHierarchy)
class OrgHierarchyAdmin(admin.ModelAdmin):
    list_display  = ('employee', 'manager', 'created_at')
    search_fields = ('employee__email', 'manager__email')
