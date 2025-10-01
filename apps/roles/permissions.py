from rest_framework.permissions import BasePermission

from apps.roles.constants import (
    ROLE_SAAS_ADMINISTRATOR,
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

        return request.user.role_assignments.filter(
            role__name=ROLE_SAAS_ADMINISTRATOR,
            organization__isnull=True,
            is_active=True
        ).exists()


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
# from .constants import ROLE_ACCOUNT_OWNER, ROLE_ACCOUNT_ADMINISTRATOR
# class IsAccountOwner(BaseRolePermission):
#     required_roles = {ROLE_ACCOUNT_OWNER}
# class IsAccountAdmin(BaseRolePermission):
#     required_roles = {ROLE_ACCOUNT_OWNER, ROLE_ACCOUNT_ADMINISTRATOR}