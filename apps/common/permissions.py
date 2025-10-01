from __future__ import annotations

from typing import Any, Iterable, Set

from rest_framework.permissions import BasePermission, SAFE_METHODS

from apps.accounts.models import Account


# ------------------------------------------------------------
# Helpers to resolve a user's assigned Account IDs (flexible)
# ------------------------------------------------------------


def _iter_ids(value: Any) -> Iterable[int]:
    """Normalise assorted iterable or queryset inputs into an ``Iterable[int]`` of IDs."""

    try:
        return value.values_list("id", flat=True)  # type: ignore[attr-defined]
    except Exception:
        try:
            return (getattr(item, "id", item) for item in value)  # type: ignore[reportUnknownParameterType]
        except Exception:
            return ()


def get_assigned_account_ids(user) -> Set[int]:
    """
    Resolve assigned account IDs for a user without hard-coding your data model.
    Supports (in order of precedence):

    - user.get_assigned_account_ids() -> Iterable[int]
    - user.assigned_accounts (M2M or queryset)
    - user.managed_accounts (M2M or queryset)
    - user.accounts (M2M or queryset)

    Fallback: empty set (no assignments).
    """
    # Method form
    if hasattr(user, "get_assigned_account_ids") and callable(user.get_assigned_account_ids):
        try:
            return set(int(x) for x in user.get_assigned_account_ids())
        except Exception:
            pass

    # Common relation names
    for attr in ("assigned_accounts", "managed_accounts", "accounts"):
        if hasattr(user, attr):
            try:
                return set(int(x) for x in _iter_ids(getattr(user, attr)))
            except Exception:
                continue
    return set()


def _user_owns_account(user, account_id: int) -> bool:
    """Return ``True`` when ``user`` owns the account with ``account_id``."""

    try:
        return Account.objects.filter(id=account_id, created_by_id=getattr(user, "id", None)).exists()
    except Exception:
        return False


# ------------------------------------------------------------
# Accounts permission
# ------------------------------------------------------------


class IsAccountAdminOrOwnerViewOnlyForManager(BasePermission):
    """
    Accounts:
      - Superadmin: full access
      - Saas Manager/Manager: VIEW ONLY (SAFE_METHODS on list/retrieve); cannot create/update/delete
      - Regular users: no list/create; can retrieve/update/patch/destroy if owner (created_by)

    Notes:
      * Object-level checks enforce owner edit for non-admin/non-staff.
      * Saas Manager cannot modify accounts even if they originally created them (per requirement).
    """

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated):
            return False

        if user.is_superuser:
            return True

        action = getattr(view, "action", None)

        if user.is_staff:
            # Saas Manager: allow list/retrieve only; both are GET (SAFE_METHODS)
            if action in {"list", "retrieve"}:
                return request.method in SAFE_METHODS
            # Block create/update/partial_update/destroy
            return False

        # Regular user (non-staff, non-admin):
        if action in {"list", "create"}:
            return False  # cannot list or create
        # Allow retrieve/update/partial_update/destroy to fall through to object check
        return action in {"retrieve", "update", "partial_update", "destroy"}

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser:
            return True

        if user.is_staff:
            # Saas Manager: may only view (SAFE_METHODS)
            return request.method in SAFE_METHODS

        # Regular users: owner can manage
        return getattr(obj, "created_by_id", None) == getattr(user, "id", None)


# ------------------------------------------------------------
# Organizations permission (with account assignments)
# ------------------------------------------------------------


class IsOrgAdminOrOwnerWithAssignments(BasePermission):
    """
    Organizations:
      - Superadmin: full access
      - Saas Manager/Manager:
          * May list organizations of accounts ASSIGNED to them
          * May create/update/patch/destroy organizations ONLY when the org's account
            is assigned to them
      - Regular users (account owners/admins):
          * May list organizations for accounts they own
          * May create organizations only under accounts they own
          * May retrieve/update/patch/destroy organizations they created or whose account they own

    Create rule detail:
      - On POST, staff must provide an assigned account; non-staff must provide an account they own.

    Object rule detail:
      - For object actions, staff must have the organization's account assigned.
      - Regular users must own the organization or its parent account.
    """

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated):
            return False

        if user.is_superuser:
            return True

        action = getattr(view, "action", None)

        if user.is_staff:
            if action == "list":
                # Saas Manager can list; queryset will be scope-filtered in the view
                return True
            if action == "create":
                # Require account in payload to be assigned
                account_id = request.data.get("account")
                try:
                    account_id = int(account_id)
                except Exception:
                    return False
                return account_id in get_assigned_account_ids(user)
            # For retrieve/update/partial_update/destroy: defer to object check
            return action in {"retrieve", "update", "partial_update", "destroy"}

        # Regular users (non-staff, non-admin)
        if action == "list":
            return True
        if action == "create":
            account_id = request.data.get("account")
            try:
                account_id = int(account_id)
            except Exception:
                return False
            return _user_owns_account(user, account_id)
        return action in {"retrieve", "update", "partial_update", "destroy"}

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser:
            return True

        if user.is_staff:
            # Saas Manager must have the org's account assigned
            account_id = getattr(getattr(obj, "account", None), "id", None)
            return account_id in get_assigned_account_ids(user)

        # Regular users: must own the object or its parent account
        if getattr(obj, "created_by_id", None) == getattr(user, "id", None):
            return True
        account = getattr(obj, "account", None)
        account_owner_id = getattr(account, "created_by_id", None)
        if account_owner_id is not None:
            return account_owner_id == getattr(user, "id", None)
        account_id = getattr(account, "id", None) if account is not None else getattr(obj, "account_id", None)
        return _user_owns_account(user, account_id)
