# apps/accounts/permissions.py
from rest_framework.permissions import BasePermission

class IsSaaSAdminOrStaff(BasePermission):
    """
    Current, test-aligned policy:
      - Allow SaaS Admin (is_superuser) OR Manager (is_staff) to access all CRUD
        on Accounts.
      - Normal users are forbidden.

    NOTE / TODO:
      - When you implement manager scoping, enforce "assigned accounts only"
        here (object-level checks).
      - If you want to enforce *admin-only* create/delete per the product doc,
        see the commented block below.
    """

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False

        # Keep it simple for now: both admin and staff have full CRUD.
        if u.is_superuser or u.is_staff:
            return True

        return False