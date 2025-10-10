from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Set

from django.conf import settings
from django.db.models import Q

from apps.common.exceptions import (
    InsufficientPermissions,
    CustomError,
    SUBSCRIPTION_LIMIT_EXCEEDED,
    TEAM_SIZE_LIMIT_EXCEEDED,
)
from rest_framework.exceptions import NotFound
from apps.accounts.services import get_assigned_account_ids
from apps.subscriptions.services import get_subscription_configuration
from apps.users.services import (
    get_user_accessible_account_ids,
    get_user_accessible_organization_ids,
    resolve_effective_permission_keys,
)


@dataclass(frozen=True)
class TeamLimits:
    """Resolved subscription limits for team operations."""

    max_teams: int | None
    max_team_members: int | None
    team_retention_days: int | None


_DEFAULT_LIMITS: Dict[str, int] = {
    "max_teams": 1000,
    "max_team_members": 1000,
    "team_retention_days": 365,
}

TEAMS_MODULE_KEY = "TEAMS_MANAGEMENT"


def _is_authenticated(user) -> bool:
    return bool(user and getattr(user, "is_authenticated", False))


def _settings_limits() -> Dict[str, int]:
    configured = getattr(settings, "TEAM_DEFAULT_LIMITS", None)
    if not configured:
        return {}
    if isinstance(configured, dict):
        return {
            str(k): int(v)
            for k, v in configured.items()
            if str(k) in _DEFAULT_LIMITS and v is not None
        }
    raise TypeError("TEAM_DEFAULT_LIMITS must be a mapping when provided.")


def _subscription_overrides(organization) -> Dict[str, Any]:
    config = get_subscription_configuration(organization, TEAMS_MODULE_KEY)
    if not isinstance(config, dict):
        return {}
    return {
        str(k): config[k] for k in _DEFAULT_LIMITS.keys() if config.get(k) is not None
    }


def _organization_overrides(organization) -> Dict[str, Any]:
    overrides: Dict[str, Any] = {}
    if hasattr(organization, "team_limit_overrides"):
        value = getattr(organization, "team_limit_overrides")
        if callable(value):
            value = value()
        if isinstance(value, dict):
            overrides.update(value)
    accessor = getattr(organization, "get_team_limit_overrides", None)
    if callable(accessor):
        value = accessor()
        if isinstance(value, dict):
            overrides.update(value)
    return {str(k): v for k, v in overrides.items() if str(k) in _DEFAULT_LIMITS}


def resolve_team_limits(organization) -> TeamLimits:
    """Return effective limits for the provided organization."""

    base = dict(_DEFAULT_LIMITS)
    base.update(_settings_limits())
    base.update(_subscription_overrides(organization))
    base.update(_organization_overrides(organization))

    def _coerce(key: str) -> int | None:
        value = base.get(key)
        if value is None:
            return None
        try:
            numeric = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be an integer or None.") from exc
        if numeric <= 0:
            return None
        return numeric

    return TeamLimits(
        max_teams=_coerce("max_teams"),
        max_team_members=_coerce("max_team_members"),
        team_retention_days=_coerce("team_retention_days"),
    )


def enforce_team_creation_limits(
    *, organization, current_count: int | None = None
) -> None:
    """Ensure the organization can create another team under subscription limits."""

    limits = resolve_team_limits(organization)
    if limits.max_teams is None:
        return
    if current_count is None:
        from apps.teams.models import Team

        current_count = Team.objects.filter(organization=organization).count()
    if current_count >= limits.max_teams:
        raise CustomError(
            code=SUBSCRIPTION_LIMIT_EXCEEDED,
            status_code=409,
            detail="Organization has reached its team limit.",
        )


def enforce_team_member_limits(*, team, current_count: int | None = None) -> None:
    """Ensure the team can accept additional members under subscription limits."""

    limits = resolve_team_limits(team.organization)
    if limits.max_team_members is None:
        return
    if current_count is None:
        current_count = team.memberships.count()
    if current_count >= limits.max_team_members:
        raise CustomError(
            code=TEAM_SIZE_LIMIT_EXCEEDED,
            status_code=400,
            detail="Team has reached its member limit.",
        )


def _organization_owner_ids(organization) -> Set[int]:
    owner_ids: Set[int] = set()
    created_by_id = getattr(organization, "created_by_id", None)
    account = getattr(organization, "account", None)
    if created_by_id:
        owner_ids.add(created_by_id)
    if account and getattr(account, "created_by_id", None):
        owner_ids.add(account.created_by_id)
    return owner_ids


def _normalize_permission_key(permission_key: Optional[str]) -> str:
    return (permission_key or "").strip().lower()


def _has_membership_permission(user, organization_id: int, permission_key: str) -> bool:
    permission_key = _normalize_permission_key(permission_key)
    if not permission_key:
        return True
    perms = {
        perm.lower()
        for perm in resolve_effective_permission_keys(user, organization_id)
    }
    if permission_key in perms:
        return True
    if permission_key == "teams:list" and "teams:read" in perms:
        return True
    if permission_key == "teams:read" and "teams:view_all" in perms:
        return True
    return False


def user_has_team_permission(
    user,
    organization,
    permission_key: str,
    *,
    team=None,
    allow_member_fallback: bool = False,
) -> bool:
    """Return True when the user has the requested permission within organization/team."""

    if not _is_authenticated(user) or organization is None:
        return False
    if user.is_superuser:
        return True
    if user.is_staff:
        return organization.account_id in get_assigned_account_ids(user)
    if user.id in _organization_owner_ids(organization):
        return True
    if _has_membership_permission(user, organization.id, permission_key):
        return True
    if allow_member_fallback and team is not None:
        from apps.teams.models import TeamMember

        return TeamMember.objects.filter(
            team=team,
            user=user,
            deleted_at__isnull=True,
            is_active=True,
        ).exists()
    return False


def filter_teams_for_user(queryset, user):
    """Scope teams to those visible to the actor."""

    if not _is_authenticated(user):
        return queryset.none()
    if user.is_superuser:
        return queryset
    if user.is_staff:
        assigned = set(get_assigned_account_ids(user))
        if not assigned:
            return queryset.none()
        return queryset.filter(organization__account_id__in=assigned)

    account_ids = get_user_accessible_account_ids(user)
    organization_ids = get_user_accessible_organization_ids(user)

    from apps.teams.models import TeamMember

    member_team_ids = TeamMember.objects.filter(
        user=user,
        deleted_at__isnull=True,
        is_active=True,
    ).values_list("team_id", flat=True)

    filters = Q()
    if account_ids:
        filters |= Q(organization__account_id__in=account_ids)
    if organization_ids:
        filters |= Q(organization_id__in=organization_ids)
    if member_team_ids:
        filters |= Q(id__in=member_team_ids)
    if not filters:
        return queryset.none()
    return queryset.filter(filters).distinct()


def ensure_user_can_create_team(user, organization) -> None:
    if not user_has_team_permission(user, organization, "teams:create"):
        raise InsufficientPermissions()


def ensure_user_can_manage_team(user, team, permission_key: str) -> None:
    if not user_has_team_permission(user, team.organization, permission_key, team=team):
        raise InsufficientPermissions()


def ensure_user_can_read_team(user, team) -> None:
    if not user_has_team_permission(
        user,
        team.organization,
        "teams:read",
        team=team,
        allow_member_fallback=True,
    ):
        raise NotFound()


def ensure_user_can_manage_members(user, team) -> None:
    if not user_has_team_permission(
        user, team.organization, "teams:manage_members", team=team
    ):
        raise InsufficientPermissions()


__all__ = [
    "TeamLimits",
    "resolve_team_limits",
    "enforce_team_creation_limits",
    "enforce_team_member_limits",
    "filter_teams_for_user",
    "ensure_user_can_create_team",
    "ensure_user_can_manage_team",
    "ensure_user_can_read_team",
    "ensure_user_can_manage_members",
]
