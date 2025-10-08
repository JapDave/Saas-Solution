from __future__ import annotations

from typing import Optional, Union
from uuid import UUID

from rest_framework.permissions import BasePermission, SAFE_METHODS

from apps.accounts.models import Account
from apps.accounts.services import get_assigned_account_ids
from apps.roles.constants import (
    ROLE_ACCOUNT_ADMINISTRATOR,
    ROLE_ACCOUNT_OWNER,
    ROLE_ORGANIZATION_ADMINISTRATOR,
    ROLE_ORGANIZATION_OWNER,
    ROLE_SAAS_ACCOUNT_MANAGER,
    ROLE_SAAS_ADMINISTRATOR,
)
from apps.roles.utils import has_permission, has_role


class AnyOf(BasePermission):
    """
    Generic permission class that passes if ANY of the provided permission classes pass.
    Permissions should be passed as uninitialized classes (e.g., AnyOf(P1, P2)).
    """
    def __init__(self, *permissions):
        # We store the instantiated permission objects
        self.permissions = [p() for p in permissions] 

    def has_permission(self, request, view):
        """Returns True if any permission in the list grants access."""
        for permission in self.permissions:
            if permission.has_permission(request, view):
                return True
        return False

class BaseRolePermission(BasePermission):
    """Base helper for simple role checks inside an organization."""

    required_roles = set()

    def _get_user_roles(self, request, view):
        """Cache the caller's role names for the current organization."""

        if hasattr(request, "_user_roles_in_org"):
            return request._user_roles_in_org

        user = getattr(request, "user", None)
        kwargs = getattr(view, "kwargs", {})
        organization_uuid = kwargs.get("organization_uuid") or kwargs.get("uuid")
        if not user or not getattr(user, "is_authenticated", False) or not organization_uuid:
            request._user_roles_in_org = set()
            return set()

        roles = user.role_assignments.filter(
            organization__uuid=organization_uuid,
            is_active=True,
        ).values_list("role__name", flat=True)

        request._user_roles_in_org = set(roles)
        return request._user_roles_in_org

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return False

        if getattr(user, "is_superuser", False):
            return True

        if has_role(user, ROLE_SAAS_ADMINISTRATOR):
            return True

        user_roles = self._get_user_roles(request, view)
        return bool(self.required_roles.intersection(user_roles))


class IsSaaSAdmin(BasePermission):
    """Grant access to SaaS administrators."""

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        return has_role(user, ROLE_SAAS_ADMINISTRATOR)


class ISSaaSAccountManager(BasePermission):
    """Grant access to SaaS account managers."""

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        return has_role(user, ROLE_SAAS_ACCOUNT_MANAGER)


class IsOrganizationOwner(BaseRolePermission):
    required_roles = {ROLE_ORGANIZATION_OWNER}


class IsOrganizationAdmin(BaseRolePermission):
    required_roles = {ROLE_ORGANIZATION_OWNER, ROLE_ORGANIZATION_ADMINISTRATOR}


class IsAccountOwner(BaseRolePermission):
    required_roles = {ROLE_ACCOUNT_OWNER}


class IsAccountAdmin(BaseRolePermission):
    required_roles = {ROLE_ACCOUNT_OWNER, ROLE_ACCOUNT_ADMINISTRATOR}


class AccountPermission(BasePermission):
    """Permission guard for the Account API."""

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False

        if user.is_superuser or has_role(user, ROLE_SAAS_ADMINISTRATOR):
            return True

        action = getattr(view, "action", None)
        if action == "list":
            return has_role(user, ROLE_SAAS_ACCOUNT_MANAGER) or getattr(user, "is_staff", False)
        if action == "create":
            return has_role(user, ROLE_SAAS_ADMINISTRATOR)
        return True  # defer to object checks

    def has_object_permission(self, request, view, obj):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False

        if user.is_superuser or has_role(user, ROLE_SAAS_ADMINISTRATOR):
            return True

        if has_role(user, ROLE_SAAS_ACCOUNT_MANAGER) or getattr(user, "is_staff", False):
            return request.method in SAFE_METHODS

        return getattr(obj, "created_by_id", None) == getattr(user, "id", None)


class OrganizationPermission(BasePermission):
    """Permission guard for the Organization API."""

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False

        if user.is_superuser or has_role(user, ROLE_SAAS_ADMINISTRATOR):
            return True

        action = getattr(view, "action", None)
        if action == "create":
            account_id = getattr(request, "data", {}).get("account")
            if account_id is None:
                return False
            try:
                account_id = int(account_id)
            except (TypeError, ValueError):
                return False

            if has_role(user, ROLE_SAAS_ACCOUNT_MANAGER) or getattr(user, "is_staff", False):
                return account_id in get_assigned_account_ids(user)

            return Account.objects.filter(id=account_id, created_by_id=user.id).exists()

        return True

    def has_object_permission(self, request, view, obj):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False

        if user.is_superuser or has_role(user, ROLE_SAAS_ADMINISTRATOR):
            return True

        assigned_accounts = get_assigned_account_ids(user)
        if has_role(user, ROLE_SAAS_ACCOUNT_MANAGER) or getattr(user, "is_staff", False):
            return getattr(obj, "account_id", None) in assigned_accounts

        org_uuid = getattr(obj, "uuid", None)
        if org_uuid and has_role(user, ROLE_ORGANIZATION_OWNER, organization_uuid=org_uuid):
            return True
        if org_uuid and has_role(user, ROLE_ORGANIZATION_ADMINISTRATOR, organization_uuid=org_uuid):
            return True

        if getattr(obj, "created_by_id", None) == getattr(user, "id", None):
            return True

        account = getattr(obj, "account", None)
        if account and getattr(account, "created_by_id", None) == getattr(user, "id", None):
            return True

        return False


class HasRole(BasePermission):
    """Generic role checker that supports organization-aware roles."""

    def __init__(self, role_name: str):
        self.role_name = role_name
        super().__init__()

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return False

        if getattr(user, "is_superuser", False):
            return True

        if has_role(user, ROLE_SAAS_ADMINISTRATOR):
            return True

        organization_uuid = None
        if hasattr(view, "kwargs"):
            organization_uuid = view.kwargs.get("organization_uuid") or view.kwargs.get("uuid")
        if not organization_uuid:
            data = getattr(request, "data", {})
            organization_uuid = data.get("organization_uuid")

        return has_role(user, self.role_name, organization_uuid=organization_uuid)


class HasPermission(BasePermission):
    """Generic permission checker that supports global and scoped permissions."""

    def __init__(self, permission_key: str, *, organization_kwarg: Optional[str] = "organization_uuid"):
        self.permission_key = permission_key
        self.organization_kwarg = organization_kwarg
        super().__init__()

    def _resolve_organization(self, request, view) -> Optional[Union[str, UUID]]:
        if self.organization_kwarg and hasattr(view, "kwargs"):
            candidate = view.kwargs.get(self.organization_kwarg)
            if candidate:
                return candidate

        if hasattr(view, "kwargs"):
            candidate = view.kwargs.get("uuid")
            if candidate:
                return candidate

        data = getattr(request, "data", {})
        if isinstance(data, dict):
            for key in ("organization_uuid", "organization"):
                candidate = data.get(key)
                if candidate:
                    return candidate
        return None

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False

        organization_identifier = self._resolve_organization(request, view)
        return has_permission(user, self.permission_key, organization_identifier)

