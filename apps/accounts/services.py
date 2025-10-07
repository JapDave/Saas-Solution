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