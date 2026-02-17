from __future__ import annotations

from typing import Optional, Union
from uuid import UUID

from rest_framework.permissions import BasePermission, SAFE_METHODS

from apps.accounts.models import Account
from apps.accounts.services import get_assigned_account_ids
from apps.common.audit import log_authorization_decision
from apps.roles.constants import (
    ROLE_ACCOUNT_ADMINISTRATOR,
    ROLE_ACCOUNT_OWNER,
    ROLE_ORGANIZATION_ADMINISTRATOR,
    ROLE_ORGANIZATION_OWNER,
    ROLE_SAAS_ACCOUNT_MANAGER,
    ROLE_SAAS_ADMINISTRATOR,
)
from apps.roles.utils import has_permission, has_role


def _log_decision(request, *, decision: bool, permission: str | None = None, roles: list[str] | None = None, reason: str | None = None, resource: dict | None = None) -> None:
    log_authorization_decision(
        request,
        decision=decision,
        permission=permission,
        roles=roles,
        reason=reason,
        resource=resource,
    )


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
        kwargs = getattr(view, "kwargs", {})
        organization_uuid = kwargs.get("organization_uuid") or kwargs.get("uuid")
        if not user or not getattr(user, "is_authenticated", False):
            _log_decision(
                request,
                decision=False,
                roles=sorted(self.required_roles),
                reason="unauthenticated",
                resource={"organization_uuid": organization_uuid},
            )
            return False

        user_roles = self._get_user_roles(request, view)
        decision = bool(self.required_roles.intersection(user_roles))
        _log_decision(
            request,
            decision=decision,
            roles=sorted(self.required_roles),
            reason=None if decision else "missing_role",
            resource={"organization_uuid": organization_uuid},
        )
        return decision


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
            _log_decision(
                request,
                decision=False,
                permission="accounts:access",
                reason="unauthenticated",
            )
            return False

        if user.is_superuser or has_role(user, ROLE_SAAS_ADMINISTRATOR):
            _log_decision(
                request,
                decision=True,
                permission="accounts:access",
                roles=[ROLE_SAAS_ADMINISTRATOR],
            )
            return True

        action = getattr(view, "action", None)
        if action == "list":
            if has_role(user, ROLE_SAAS_ACCOUNT_MANAGER) or getattr(user, "is_staff", False):
                assigned = get_assigned_account_ids(user)
                decision = bool(assigned)
            else:
                decision = False
            _log_decision(
                request,
                decision=decision,
                permission="accounts:list",
                roles=[ROLE_SAAS_ACCOUNT_MANAGER],
                reason=None if decision else "missing_role",
            )
            return decision
        if action == "create":
            decision = has_role(user, ROLE_SAAS_ADMINISTRATOR)
            _log_decision(
                request,
                decision=decision,
                permission="accounts:create",
                roles=[ROLE_SAAS_ADMINISTRATOR],
                reason=None if decision else "missing_role",
            )
            return decision
        _log_decision(
            request,
            decision=True,
            permission="accounts:object",
            reason="defer_object",
        )
        return True  # defer to object checks

    def has_object_permission(self, request, view, obj):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            _log_decision(
                request,
                decision=False,
                permission="accounts:object",
                reason="unauthenticated",
                resource={"object_id": getattr(obj, "id", None)},
            )
            return False

        if user.is_superuser or has_role(user, ROLE_SAAS_ADMINISTRATOR):
            _log_decision(
                request,
                decision=True,
                permission="accounts:object",
                roles=[ROLE_SAAS_ADMINISTRATOR],
                resource={"object_id": getattr(obj, "id", None)},
            )
            return True

        if has_role(user, ROLE_SAAS_ACCOUNT_MANAGER) or getattr(user, "is_staff", False):
            assigned = get_assigned_account_ids(user)
            decision = bool(assigned) and getattr(obj, "id", None) in assigned and request.method in SAFE_METHODS
            _log_decision(
                request,
                decision=decision,
                permission="accounts:read",
                roles=[ROLE_SAAS_ACCOUNT_MANAGER],
                reason=None if decision else "unsafe_method",
                resource={"object_id": getattr(obj, "id", None)},
            )
            return decision

        decision = getattr(obj, "created_by_id", None) == getattr(user, "id", None)
        _log_decision(
            request,
            decision=decision,
            permission="accounts:owner",
            reason=None if decision else "not_owner",
            resource={"object_id": getattr(obj, "id", None)},
        )
        return decision


class OrganizationPermission(BasePermission):
    """Permission guard for the Organization API."""

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            _log_decision(
                request,
                decision=False,
                permission="organizations:access",
                reason="unauthenticated",
            )
            return False

        if user.is_superuser or has_role(user, ROLE_SAAS_ADMINISTRATOR):
            _log_decision(
                request,
                decision=True,
                permission="organizations:access",
                roles=[ROLE_SAAS_ADMINISTRATOR],
            )
            return True

        action = getattr(view, "action", None)
        if action == "create":
            account_id = getattr(request, "data", {}).get("account")
            if account_id is None:
                _log_decision(
                    request,
                    decision=False,
                    permission="organizations:create",
                    reason="missing_account",
                )
                return False
            try:
                account_id = int(account_id)
            except (TypeError, ValueError):
                _log_decision(
                    request,
                    decision=False,
                    permission="organizations:create",
                    reason="invalid_account",
                )
                return False

            if has_role(user, ROLE_SAAS_ACCOUNT_MANAGER) or getattr(user, "is_staff", False):
                assigned = get_assigned_account_ids(user)
                decision = bool(assigned) and account_id in assigned
                _log_decision(
                    request,
                    decision=decision,
                    permission="organizations:create",
                    roles=[ROLE_SAAS_ACCOUNT_MANAGER],
                    reason=None if decision else "account_not_assigned",
                    resource={"account_id": account_id},
                )
                return decision

            decision = Account.objects.filter(id=account_id, created_by_id=user.id).exists()
            _log_decision(
                request,
                decision=decision,
                permission="organizations:create",
                reason=None if decision else "account_not_owned",
                resource={"account_id": account_id},
            )
            return decision

        _log_decision(
            request,
            decision=True,
            permission="organizations:object",
            reason="defer_object",
        )
        return True

    def has_object_permission(self, request, view, obj):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            _log_decision(
                request,
                decision=False,
                permission="organizations:object",
                reason="unauthenticated",
                resource={"organization_id": getattr(obj, "id", None)},
            )
            return False

        if user.is_superuser or has_role(user, ROLE_SAAS_ADMINISTRATOR):
            _log_decision(
                request,
                decision=True,
                permission="organizations:object",
                roles=[ROLE_SAAS_ADMINISTRATOR],
                resource={"organization_id": getattr(obj, "id", None)},
            )
            return True

        assigned_accounts = get_assigned_account_ids(user)
        if has_role(user, ROLE_SAAS_ACCOUNT_MANAGER) or getattr(user, "is_staff", False):
            decision = getattr(obj, "account_id", None) in assigned_accounts
            _log_decision(
                request,
                decision=decision,
                permission="organizations:object",
                roles=[ROLE_SAAS_ACCOUNT_MANAGER],
                reason=None if decision else "account_not_assigned",
                resource={"organization_id": getattr(obj, "id", None)},
            )
            return decision

        org_uuid = getattr(obj, "uuid", None)
        if org_uuid and has_role(user, ROLE_ORGANIZATION_OWNER, organization_uuid=org_uuid):
            _log_decision(
                request,
                decision=True,
                permission="organizations:owner",
                roles=[ROLE_ORGANIZATION_OWNER],
                resource={"organization_uuid": str(org_uuid)},
            )
            return True
        if org_uuid and has_role(user, ROLE_ORGANIZATION_ADMINISTRATOR, organization_uuid=org_uuid):
            _log_decision(
                request,
                decision=True,
                permission="organizations:admin",
                roles=[ROLE_ORGANIZATION_ADMINISTRATOR],
                resource={"organization_uuid": str(org_uuid)},
            )
            return True

        if getattr(obj, "created_by_id", None) == getattr(user, "id", None):
            _log_decision(
                request,
                decision=True,
                permission="organizations:creator",
                resource={"organization_id": getattr(obj, "id", None)},
            )
            return True

        account = getattr(obj, "account", None)
        if account and getattr(account, "created_by_id", None) == getattr(user, "id", None):
            _log_decision(
                request,
                decision=True,
                permission="organizations:account_owner",
                resource={"organization_id": getattr(obj, "id", None)},
            )
            return True

        _log_decision(
            request,
            decision=False,
            permission="organizations:object",
            reason="no_access",
            resource={"organization_id": getattr(obj, "id", None)},
        )
        return False


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
        return has_permission(request.user, self.permission_key, self.organization_uuid)
