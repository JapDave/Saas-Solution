from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, Optional, Set

from django.contrib.auth import get_user_model
from django.db.models import Q

from apps.accounts.models import Account
from apps.common.exceptions import CannotDeactivateOwner, CannotDeleteOwner, InsufficientPermissions
from apps.common.permissions import get_assigned_account_ids
from apps.organizations.models import Organization

from .models import UserOrganization

User = get_user_model()


def _is_authenticated(user) -> bool:
    return bool(user and getattr(user, "is_authenticated", False))


def actor_membership_permissions(user, *, organization_id: Optional[int] = None) -> Dict[int, Set[str]]:
    """Return mapping of organization_id -> permission set for the actor."""
    permissions_map: Dict[int, Set[str]] = defaultdict(set)
    if not _is_authenticated(user):
        return permissions_map
    qs = UserOrganization.objects.filter(user=user)
    if organization_id is not None:
        qs = qs.filter(organization_id=organization_id)
    for membership in qs:
        permissions_map[membership.organization_id].update(perm.strip() for perm in membership.permission_keys or [])
    return permissions_map


def actor_accessible_account_ids(user) -> Set[int]:
    if not _is_authenticated(user):
        return set()
    if user.is_superuser:
        return set(Account.objects.values_list("id", flat=True))
    if user.is_staff:
        return set(get_assigned_account_ids(user))
    owned = set(
        Account.objects.filter(created_by_id=user.id).values_list("id", flat=True)
    )
    membership_accounts = set(
        UserOrganization.objects.filter(user=user)
        .values_list("organization__account_id", flat=True)
    )
    return owned | membership_accounts


def actor_accessible_organization_ids(user) -> Set[int]:
    if not _is_authenticated(user):
        return set()
    if user.is_superuser:
        return set(Organization.objects.values_list("id", flat=True))
    if user.is_staff:
        account_ids = get_assigned_account_ids(user)
        if not account_ids:
            return set()
        return set(
            Organization.objects.filter(account_id__in=account_ids).values_list("id", flat=True)
        )
    owned = set(
        Organization.objects.filter(
            Q(created_by_id=user.id) | Q(account__created_by_id=user.id)
        ).values_list("id", flat=True)
    )
    membership_orgs = set(
        UserOrganization.objects.filter(user=user).values_list("organization_id", flat=True)
    )
    return owned | membership_orgs


def membership_has_permission(user, organization_id: int, permission_key: str) -> bool:
    permission_key = (permission_key or "").lower()
    if not permission_key:
        return True
    permissions_map = actor_membership_permissions(user)
    return permission_key in {perm.lower() for perm in permissions_map.get(organization_id, set())}


def assert_actor_can_manage_organization(actor, organization: Organization, *, permission_key: str = "") -> None:
    if not _is_authenticated(actor):
        raise InsufficientPermissions()
    if actor.is_superuser:
        return
    if actor.is_staff:
        if organization.account_id in get_assigned_account_ids(actor):
            return
        raise InsufficientPermissions()
    if organization.account.created_by_id == actor.id or organization.created_by_id == actor.id:
        return
    if membership_has_permission(actor, organization.id, permission_key):
        return
    raise InsufficientPermissions()


def user_membership_account_ids(user) -> Set[int]:
    return set(
        UserOrganization.all_objects.filter(user=user).values_list("organization__account_id", flat=True)
    )


def assert_actor_can_manage_user(actor, target, *, require_permission: Optional[str] = None, allow_self: bool = False) -> None:
    if not _is_authenticated(actor):
        raise InsufficientPermissions()
    if actor.is_superuser:
        return
    if allow_self and actor.id == target.id:
        return
    if actor.is_staff:
        assigned_accounts = get_assigned_account_ids(actor)
        if assigned_accounts & user_membership_account_ids(target):
            return
        raise InsufficientPermissions()
    actor_accounts = actor_accessible_account_ids(actor)
    target_accounts = user_membership_account_ids(target)
    if actor_accounts & target_accounts:
        if Account.objects.filter(created_by_id=actor.id, id__in=target_accounts).exists():
            return
        if Organization.objects.filter(created_by_id=actor.id, account_id__in=target_accounts).exists():
            return
        if not require_permission:
            return
        overlapping_orgs = UserOrganization.objects.filter(
            user=target,
            organization__account_id__in=actor_accounts,
        ).values_list("organization_id", flat=True)
        for org_id in overlapping_orgs:
            if membership_has_permission(actor, org_id, require_permission):
                return
        raise InsufficientPermissions()
    if Account.objects.filter(created_by_id=actor.id, id__in=target_accounts).exists():
        return
    if Organization.objects.filter(created_by_id=actor.id, account_id__in=target_accounts).exists():
        return
    raise InsufficientPermissions()


def resolve_effective_permission_keys(user, organization_id: int) -> Set[str]:
    """Resolve permission keys for a user within an organization.

    This is a forward-compatible entry point so that a future role module can
    contribute permissions without changing call sites in the user domain.
    """
    permissions = set(actor_membership_permissions(user, organization_id=organization_id).get(organization_id, set()))
    try:
        from apps.roles import services as role_services  # type: ignore
    except ModuleNotFoundError:
        role_services = None
    if role_services and hasattr(role_services, "resolve_user_permissions"):
        additional = role_services.resolve_user_permissions(user=user, organization_id=organization_id)
        if additional:
            permissions.update(additional)
    return permissions


def is_account_or_organization_owner(user) -> bool:
    if not _is_authenticated(user):
        return False
    owns_account = Account.objects.filter(created_by_id=user.id, deleted_at__isnull=True).exists()
    if owns_account:
        return True
    owns_org = Organization.objects.filter(created_by_id=user.id, deleted_at__isnull=True).exists()
    return owns_org


def ensure_user_not_owner_for_deactivate(target) -> None:
    if is_account_or_organization_owner(target):
        raise CannotDeactivateOwner()


def ensure_user_not_owner_for_delete(target) -> None:
    if is_account_or_organization_owner(target):
        raise CannotDeleteOwner()
