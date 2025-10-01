from django.contrib import admin
from apps.roles.models import Role, RoleAssignment

@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'role_type', 'is_active')
    list_filter = ('role_type', 'is_active')
    search_fields = ('name', 'description')


@admin.register(RoleAssignment)
class RoleAssignmentAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'organization', 'assigned_by', 'assigned_at')
    list_filter = ('role__role_type', 'organization')
    search_fields = ('user__username', 'role__name')
