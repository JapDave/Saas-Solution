# apps/accounts/permissions.py
from rest_framework.permissions import BasePermission

def _is_saas_admin(user) -> bool:
    return bool(getattr(user, "is_saas_admin", False))

class IsSaaSAdminOrStaff(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and (u.is_staff or _is_saas_admin(u)))

class IsSaaSAdminOnly(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and _is_saas_admin(u))
