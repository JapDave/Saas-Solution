from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Set

from django.utils import timezone

from apps.channels.definitions import (
    CHANNEL_INSTANCE_PERMISSION_KEYS,
    DEFAULT_SUBSCRIPTION_CHANNEL_CONFIG,
)
from apps.channels.models import Channel, ChannelAccessGrant
from apps.roles.utils import has_role
from apps.subscriptions.services import get_subscription_configuration
from apps.teams.models import TeamMember
from apps.users.services import resolve_effective_permission_keys
from apps.common.exceptions import CustomError, INSUFFICIENT_PERMISSIONS

CHANNELS_MODULE_KEY = "CHANNELS_MANAGEMENT"

@dataclass(frozen=True)
class ChannelLimit:
    enabled: bool
    max_instances: int


def resolve_channel_limits(organization) -> Dict[str, ChannelLimit]:
    config = get_subscription_configuration(organization, CHANNELS_MODULE_KEY) or {}
    enabled_config = (config.get("enabledChannelTypes") or {}).copy()
    limits: Dict[str, ChannelLimit] = {}
    for channel_type, defaults in DEFAULT_SUBSCRIPTION_CHANNEL_CONFIG.items():
        merged = {**defaults, **enabled_config.get(channel_type, {})}
        limits[channel_type] = ChannelLimit(
            enabled=bool(merged.get("enabled", False)),
            max_instances=max(int(merged.get("maxInstances", defaults["maxInstances"])), 0),
        )
    return limits


def ensure_channel_type_enabled(organization, channel_type: str):
    limits = resolve_channel_limits(organization)
    limit = limits.get(channel_type)
    if not limit or not limit.enabled:
        raise CustomError(code="CHANNEL_TYPE_NOT_ENABLED", status_code=400, detail="Channel type not enabled.")
    return limit


def enforce_channel_instance_limit(organization, channel_type: str):
    limit = ensure_channel_type_enabled(organization, channel_type)
    count = Channel.all_objects.filter(
        organization=organization,
        channel_type=channel_type,
        state__in=[Channel.ChannelState.ACTIVE, Channel.ChannelState.INACTIVE],
    ).count()
    if count >= limit.max_instances:
        raise CustomError(
            code="CHANNEL_LIMIT_EXCEEDED",
            status_code=409,
            detail=f"{count}/{limit.max_instances} instances used for {channel_type}.",
        )


def user_has_organization_channel_permission(user, organization, permission_key: str) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    permissions = resolve_effective_permission_keys(user, organization.id)
    if permission_key in permissions or "channels:admin" in permissions:
        return True
    return False


def ensure_org_channel_permission(user, organization, permission_key: str):
    if not user_has_organization_channel_permission(user, organization, permission_key):
        raise CustomError(code=INSUFFICIENT_PERMISSIONS, status_code=403, detail="Insufficient permissions.")


def user_has_channel_acl(user, channel: Channel, permission_key: str) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser or channel.created_by_id == getattr(user, "id", None):
        return True
    if user_has_organization_channel_permission(user, channel.organization, "channels:read"):
        return True
    # User-specific grants
    if ChannelAccessGrant.objects.filter(
        channel=channel,
        subject_type=ChannelAccessGrant.SubjectType.USER,
        subject_user=user,
        revoked_at__isnull=True,
        permissions__contains=[permission_key],
    ).exists():
        return True
    # Team grants
    team_ids = TeamMember.objects.filter(
        user=user,
        team__organization=channel.organization,
        deleted_at__isnull=True,
        is_active=True,
    ).values_list("team_id", flat=True)
    if not team_ids:
        return False
    return ChannelAccessGrant.objects.filter(
        channel=channel,
        subject_type=ChannelAccessGrant.SubjectType.TEAM,
        subject_team_id__in=team_ids,
        revoked_at__isnull=True,
        permissions__contains=[permission_key],
    ).exists()


def ensure_channel_acl(user, channel, permission_key: str):
    if not user_has_channel_acl(user, channel, permission_key):
        raise CustomError(code=INSUFFICIENT_PERMISSIONS, status_code=403, detail="Insufficient permissions.")


def revoke_channel_grants(channel: Channel):
    ChannelAccessGrant.objects.filter(channel=channel, revoked_at__isnull=True).update(revoked_at=timezone.now())
