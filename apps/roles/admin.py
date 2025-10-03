from django.contrib import admin
from apps.roles.models import Role, RoleAssignment


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'role_type', 'is_active', 'deleted_at')
    list_filter = ('role_type', 'is_active', 'organization')
    search_fields = ('name', 'description')

    def save_model(self, request, obj, form, change):
        """
        When saving from the admin, if the object was soft-deleted,
        this will restore it.
        """
        obj.deleted_at = None
        super().save_model(request, obj, form, change)


@admin.register(RoleAssignment)
class RoleAssignmentAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'organization', 'assigned_by', 'assigned_at', 'deleted_at')
    list_filter = ('role__role_type', 'organization')
    search_fields = ('user__username', 'role__name')
