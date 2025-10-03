from uuid import UUID

from rest_framework.permissions import BasePermission

from apps.roles.utils import has_role, has_permission

from apps.roles.constants import (
    ROLE_SAAS_ADMINISTRATOR,
    ROLE_SAAS_ACCOUNT_MANAGER,
    ROLE_ORGANIZATION_ADMINISTRATOR,
    ROLE_ORGANIZATION_OWNER,
)


class BaseRolePermission(BasePermission):
    """
    Base permission class for checking user roles within an organization.
    Subclasses must define a `required_roles` set of role names.
    """

    required_roles = set()

    def _get_user_roles(self, request, view):
        """Retrieves user roles from the request object, set by RoleMiddleware."""
        return getattr(request, "_user_roles_in_org", set())

    def _get_user_roles(self, request, view):
        """
        Caches the user's role names for the current organization in the request
        to avoid redundant database queries.
        """
        if hasattr(request, "_user_roles_in_org"):
            return request._user_roles_in_org

        user = request.user
        organization_uuid = view.kwargs.get("organization_uuid")

        if not user or not user.is_authenticated or not organization_uuid:
            request._user_roles_in_org = set()
            return set()

        roles = user.role_assignments.filter(
            organization__uuid=organization_uuid, is_active=True
        ).values_list("role__name", flat=True)

        request._user_roles_in_org = set(roles)
        return request._user_roles_in_org

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        user_roles = self._get_user_roles(request, view)
        # Check if the user has any of the required roles
        return not self.required_roles.isdisjoint(user_roles)


class IsSaaSAdmin(BasePermission):
    """
    Checks if the user has the global 'SaaS Administrator' role.
    This role is not tied to a specific organization.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return has_role(request.user, ROLE_SAAS_ADMINISTRATOR)


class ISSaaSAccountManager(BasePermission):
    """
    Checks if the user has the global 'SaaS Account Manager' role.
    This role is not tied to a specific organization.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return has_role(request.user, ROLE_SAAS_ACCOUNT_MANAGER)


class IsOrganizationOwner(BaseRolePermission):
    """
    Checks if the user is an 'Organization Owner'.
    """

    required_roles = {ROLE_ORGANIZATION_OWNER}


class IsOrganizationAdmin(BaseRolePermission):
    """
    Checks if the user is an 'Organization Administrator' or 'Organization Owner'.
    An owner is implicitly an administrator.
    """

    required_roles = {ROLE_ORGANIZATION_OWNER, ROLE_ORGANIZATION_ADMINISTRATOR}


# You can continue this pattern for Account-level roles
# Note: These would likely be used on different endpoints that are
# nested under an account_uuid instead of an organization_uuid.
from .constants import ROLE_ACCOUNT_OWNER, ROLE_ACCOUNT_ADMINISTRATOR
class IsAccountOwner(BaseRolePermission):
    required_roles = {ROLE_ACCOUNT_OWNER}

class IsAccountAdmin(BaseRolePermission):
    required_roles = {ROLE_ACCOUNT_OWNER, ROLE_ACCOUNT_ADMINISTRATOR}


class HasRole(BasePermission):
    """
    A generic permission class that checks if a user has a specific role.

    Usage:
        permission_classes = [HasRole("Organization Owner")]
    """

    def __init__(self, role_name: str):
        self.role_name = role_name
        super().__init__()

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # For organization-specific roles, the view must provide the org_uuid
        organization_uuid = view.kwargs.get("organization_uuid")

        return has_role(
            request.user, self.role_name, organization_uuid=organization_uuid
        )


class HasPermission(BasePermission):
    """
    A generic permission class that checks if a user has a specific permission key.

    Usage:
        permission_classes = [HasPermission("some.permission.key", "<organization_uuid>")]
    """

    def __init__(self, permission_key: str, organization_uuid: str | UUID):
        self.permission_key = permission_key
        self.organization_uuid = organization_uuid

        super().__init__()

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False


        return has_permission(
            request.user, self.permission_key, self.organization_uuid
        )
