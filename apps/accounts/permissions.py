from rest_framework.permissions import BasePermission

def _is_saas_admin(user) -> bool:
    # If you maintain a platform role flag, wire it here
    return getattr(user, "is_saas_admin", False)

class IsSaaSAdminOrStaff(BasePermission):
    """Allow only SaaS Administrator or Django staff to access Account APIs."""
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and (u.is_staff or _is_saas_admin(u)))
