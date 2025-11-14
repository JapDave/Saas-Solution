from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.common.exceptions import (
    CustomError,
    DRAFT_ALREADY_EXISTS,
    FLOW_VERSION_CONFLICT,
    INSUFFICIENT_PERMISSIONS,
    NO_ACTIVE_VERSION,
    NO_PUBLISHED_VERSION,
    PREVIOUS_VERSION_REQUIRED,
    SUBSCRIPTION_LIMIT_EXCEEDED,
)
from apps.flows.models import Flow, FlowVersion
from apps.flows.validators import validate_flow_configurations, validate_flow_json
from apps.subscriptions.services import get_subscription_configuration
from apps.users.services import resolve_effective_permission_keys

FLOWS_MODULE_KEY = "FLOWS_MANAGEMENT"
DEFAULT_MAX_FLOWS = 10


@dataclass(frozen=True)
class FlowLimits:
    max_flows: int


def _coerce_positive_int(value, default: int) -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return default
    return numeric if numeric > 0 else default


def resolve_flow_limits(organization) -> FlowLimits:
    config = get_subscription_configuration(organization, FLOWS_MODULE_KEY) or {}
    limit = _coerce_positive_int(config.get("flows_max_flows_per_org"), DEFAULT_MAX_FLOWS)
    return FlowLimits(max_flows=limit or DEFAULT_MAX_FLOWS)


def enforce_flow_limit(organization):
    limits = resolve_flow_limits(organization)
    current = Flow.objects.filter(organization=organization).count()
    if current >= limits.max_flows:
        raise CustomError(
            code=SUBSCRIPTION_LIMIT_EXCEEDED,
            status_code=403,
            detail="Organization has reached its maximum number of flows.",
        )


def user_has_flow_permission(user, organization, permission_key: str) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    permissions = {perm.lower() for perm in resolve_effective_permission_keys(user, organization.id)}
    target = (permission_key or "").lower()
    if not target:
        return True
    return target in permissions or "agents:admin" in permissions


def ensure_flow_permission(user, organization, permission_key: str):
    if not user_has_flow_permission(user, organization, permission_key):
        raise CustomError(code=INSUFFICIENT_PERMISSIONS, status_code=403, detail="Insufficient permissions.")


def next_version_number(flow: Flow) -> int:
    latest = flow.versions.aggregate(max_version=Max("version_number")).get("max_version") or 0
    return latest + 1


def latest_version(flow: Flow) -> Optional[FlowVersion]:
    return flow.versions.order_by("-version_number").first()


def _require_previous_version(flow: Flow, previous_version_uuid: Optional[str]) -> Optional[FlowVersion]:
    current = latest_version(flow)
    if current is None:
        return None
    if not previous_version_uuid:
        raise CustomError(
            code=PREVIOUS_VERSION_REQUIRED,
            status_code=400,
            detail="previousVersionId is required.",
        )
    if str(current.uuid) != str(previous_version_uuid):
        raise CustomError(
            code=FLOW_VERSION_CONFLICT,
            status_code=409,
            detail=f"Flow has moved to version {current.version_number}.",
        )
    return current


def _update_flow_metadata(flow: Flow, *, name=None, description=None, flow_configurations=None, actor=None):
    has_changes = False
    if name is not None:
        new_name = name.strip()
        if new_name and new_name != flow.name:
            flow.name = new_name
            has_changes = True
    if description is not None and description != flow.description:
        flow.description = description.strip()
        has_changes = True
    if flow_configurations is not None:
        sanitized = validate_flow_configurations(flow_configurations)
        if sanitized != flow.flow_configurations:
            flow.flow_configurations = sanitized
            has_changes = True
    if has_changes:
        flow.updated_by = actor
        flow.full_clean()
        flow.save(update_fields=["name", "description", "flow_configurations", "updated_by", "updated_at"])


@transaction.atomic
def create_flow(
    *,
    organization,
    name: str,
    description: str = "",
    flow_configurations: Optional[dict] = None,
    flow_json: dict,
    actor,
) -> Flow:
    enforce_flow_limit(organization)
    sanitized_configs = validate_flow_configurations(flow_configurations or {})
    sanitized_json = validate_flow_json(flow_json)
    flow = Flow(
        organization=organization,
        name=name.strip(),
        description=(description or "").strip(),
        flow_configurations=sanitized_configs,
        created_by=actor,
        updated_by=actor,
    )
    flow.full_clean()
    flow.save()

    FlowVersion.objects.create(
        flow=flow,
        version_number=1,
        name=flow.name,
        description=flow.description,
        flow_configurations=sanitized_configs,
        flow_json=sanitized_json,
        state=FlowVersion.FlowVersionState.DRAFT,
        created_by=actor,
    )
    return flow


def _set_active(flow: Flow, state: str, active: bool):
    FlowVersion.objects.filter(flow=flow, state=state, is_active=True).update(is_active=active, updated_at=timezone.now())


@transaction.atomic
def save_draft_version(
    flow: Flow,
    *,
    actor,
    flow_json: dict,
    flow_configurations: Optional[dict] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
    previous_version_uuid: Optional[str] = None,
) -> FlowVersion:
    existing_versions = flow.versions.exists()
    if existing_versions:
        _require_previous_version(flow, previous_version_uuid)

    _update_flow_metadata(
        flow,
        name=name or flow.name,
        description=description if description is not None else flow.description,
        flow_configurations=flow_configurations or flow.flow_configurations,
        actor=actor,
    )

    FlowVersion.objects.filter(flow=flow, state=FlowVersion.FlowVersionState.DRAFT, is_active=True).update(
        is_active=False, updated_at=timezone.now()
    )
    version = FlowVersion.objects.create(
        flow=flow,
        version_number=next_version_number(flow),
        name=flow.name,
        description=flow.description,
        flow_configurations=flow.flow_configurations,
        flow_json=validate_flow_json(flow_json),
        state=FlowVersion.FlowVersionState.DRAFT,
        created_by=actor,
    )
    return version


def _active_version(flow: Flow, state: str) -> FlowVersion:
    version = flow.versions.filter(state=state, is_active=True).order_by("-version_number").first()
    if not version:
        raise CustomError(code=NO_ACTIVE_VERSION, status_code=404, detail=f"No active {state} version found.")
    return version


@transaction.atomic
def publish_flow(flow: Flow, *, actor) -> FlowVersion:
    draft = flow.versions.filter(state=FlowVersion.FlowVersionState.DRAFT, is_active=True).order_by("-version_number").first()
    if not draft:
        raise CustomError(code=NO_ACTIVE_VERSION, status_code=404, detail="No active draft to publish.")
    FlowVersion.objects.filter(flow=flow, state=FlowVersion.FlowVersionState.PUBLISHED, is_active=True).update(
        is_active=False, updated_at=timezone.now()
    )
    draft.state = FlowVersion.FlowVersionState.PUBLISHED
    draft.is_active = True
    draft.updated_at = timezone.now()
    draft.save(update_fields=["state", "is_active", "updated_at"])
    flow.updated_by = actor
    flow.save(update_fields=["updated_by", "updated_at"])
    return draft


@transaction.atomic
def disable_flow(flow: Flow, *, actor) -> FlowVersion:
    published = flow.versions.filter(state=FlowVersion.FlowVersionState.PUBLISHED, is_active=True).first()
    if not published:
        raise CustomError(code=NO_PUBLISHED_VERSION, status_code=404, detail="No published version to disable.")
    FlowVersion.objects.filter(flow=flow, state=FlowVersion.FlowVersionState.DISABLED, is_active=True).update(
        is_active=False, updated_at=timezone.now()
    )
    published.state = FlowVersion.FlowVersionState.DISABLED
    published.is_active = True
    published.updated_at = timezone.now()
    published.save(update_fields=["state", "is_active", "updated_at"])
    flow.updated_by = actor
    flow.save(update_fields=["updated_by", "updated_at"])
    return published


@transaction.atomic
def enable_flow(flow: Flow, *, actor) -> FlowVersion:
    disabled = flow.versions.filter(state=FlowVersion.FlowVersionState.DISABLED, is_active=True).first()
    if not disabled:
        raise CustomError(code=NO_ACTIVE_VERSION, status_code=404, detail="No disabled version to enable.")
    FlowVersion.objects.filter(flow=flow, state=FlowVersion.FlowVersionState.PUBLISHED, is_active=True).update(
        is_active=False, updated_at=timezone.now()
    )
    disabled.state = FlowVersion.FlowVersionState.PUBLISHED
    disabled.is_active = True
    disabled.updated_at = timezone.now()
    disabled.save(update_fields=["state", "is_active", "updated_at"])
    flow.updated_by = actor
    flow.save(update_fields=["updated_by", "updated_at"])
    return disabled


@transaction.atomic
def create_draft_from_published(flow: Flow, *, actor) -> FlowVersion:
    existing_draft = flow.versions.filter(state=FlowVersion.FlowVersionState.DRAFT, is_active=True).exists()
    if existing_draft:
        raise CustomError(code=DRAFT_ALREADY_EXISTS, status_code=400, detail="Draft already exists.")
    published = flow.versions.filter(state=FlowVersion.FlowVersionState.PUBLISHED, is_active=True).first()
    if not published:
        raise CustomError(code=NO_PUBLISHED_VERSION, status_code=404, detail="No published version to copy.")
    version = FlowVersion.objects.create(
        flow=flow,
        version_number=next_version_number(flow),
        name=published.name,
        description=published.description,
        flow_configurations=published.flow_configurations,
        flow_json=published.flow_json,
        state=FlowVersion.FlowVersionState.DRAFT,
        created_by=actor,
    )
    return version


def _clone_name(base_name: str, organization) -> str:
    candidate = f"Copy of {base_name}"
    existing = set(
        Flow.all_objects.filter(organization=organization, name__istartswith=candidate).values_list("name", flat=True)
    )
    if candidate not in existing:
        return candidate
    suffix = 2
    while True:
        option = f"{candidate} ({suffix})"
        if option not in existing:
            return option
        suffix += 1


@transaction.atomic
def clone_flow(flow: Flow, *, actor) -> Flow:
    enforce_flow_limit(flow.organization)
    new_flow = Flow(
        organization=flow.organization,
        name=_clone_name(flow.name, flow.organization),
        description=flow.description,
        flow_configurations=flow.flow_configurations,
        created_by=actor,
        updated_by=actor,
    )
    new_flow.full_clean()
    new_flow.save()

    next_number = 1
    published = flow.versions.filter(state=FlowVersion.FlowVersionState.PUBLISHED, is_active=True).first()
    draft = flow.versions.filter(state=FlowVersion.FlowVersionState.DRAFT, is_active=True).first()

    if published:
        FlowVersion.objects.create(
            flow=new_flow,
            version_number=next_number,
            name=published.name,
            description=published.description,
            flow_configurations=published.flow_configurations,
            flow_json=published.flow_json,
            state=FlowVersion.FlowVersionState.PUBLISHED,
            created_by=actor,
        )
        next_number += 1

    if draft:
        FlowVersion.objects.create(
            flow=new_flow,
            version_number=next_number,
            name=draft.name,
            description=draft.description,
            flow_configurations=draft.flow_configurations,
            flow_json=draft.flow_json,
            state=FlowVersion.FlowVersionState.DRAFT,
            created_by=actor,
        )
    return new_flow


@transaction.atomic
def restore_flow(flow: Flow, *, actor):
    if flow.deleted_at is None:
        return
    flow.deleted_at = None
    flow.updated_by = actor
    flow.save(update_fields=["deleted_at", "updated_by", "updated_at"])


@transaction.atomic
def delete_flow(flow: Flow, *, actor):
    if flow.deleted_at is not None:
        return
    flow.updated_by = actor
    flow.save(update_fields=["updated_by", "updated_at"])
    flow.delete()


__all__ = [
    "FLOWS_MODULE_KEY",
    "FlowLimits",
    "clone_flow",
    "create_draft_from_published",
    "create_flow",
    "delete_flow",
    "disable_flow",
    "enable_flow",
    "enforce_flow_limit",
    "ensure_flow_permission",
    "latest_version",
    "next_version_number",
    "publish_flow",
    "resolve_flow_limits",
    "restore_flow",
    "save_draft_version",
    "user_has_flow_permission",
]
