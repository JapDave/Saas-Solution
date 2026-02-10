from __future__ import annotations

from dataclasses import dataclass
import time

from apps.agents.definitions import get_tool_definition
from apps.agents.services import enable_tool_for_organization, disable_tool_for_organization
from apps.agents.validators import validate_tools_configuration
from apps.agents.models import OrganizationEnabledTool
from django.core.exceptions import ValidationError

from apps.common.exceptions import (
    CustomError,
    INSUFFICIENT_PERMISSIONS,
    INVALID_CONFIGURATION,
    INVALID_URL_FORMAT,
    INVALID_UUID_FORMAT,
    KB_COLLECTION_NOT_FOUND,
    MAX_TOOLS_EXCEEDED,
    TOOL_ALREADY_DISABLED,
    TOOL_DUPLICATE,
    TOOL_NOT_FOUND,
    TOOL_NOT_ENABLED,
)
from apps.knowledge_base.models import Collection
from apps.subscriptions.services import get_subscription_configuration
from apps.users.services import resolve_effective_permission_keys
from apps.accounts.services import get_assigned_account_ids
from apps.roles.constants import ROLE_SAAS_ADMINISTRATOR, ROLE_SAAS_ACCOUNT_MANAGER
from apps.roles.utils import has_role
from apps.common.models import AuditLog
from apps.common.audit import get_audit_context, get_client_ip, get_user_agent
from apps.tools.telemetry import (
    inc_tool_enabled,
    inc_tool_disabled,
)

TOOLS_MODULE_KEY = "TOOLS_MANAGEMENT"


@dataclass(frozen=True)
class ToolLimits:
    max_enabled: int


DEFAULT_LIMITS = ToolLimits(max_enabled=50)


def resolve_tool_limits(organization) -> ToolLimits:
    config = get_subscription_configuration(organization, TOOLS_MODULE_KEY) or {}
    return ToolLimits(
        max_enabled=int(config.get("tools_max_enabled_per_org", DEFAULT_LIMITS.max_enabled)),
    )


def enforce_tool_limit(organization):
    limits = resolve_tool_limits(organization)
    count = OrganizationEnabledTool.objects.filter(
        organization=organization, disabled_at__isnull=True
    ).count()
    if count >= limits.max_enabled:
        raise CustomError(
            code=MAX_TOOLS_EXCEEDED,
            status_code=409,
            detail=f"{count}/{limits.max_enabled} tools enabled.",
        )


def ensure_tool_permission(user, organization, permission_key: str):
    if not user or not getattr(user, "is_authenticated", False):
        raise CustomError(code=INSUFFICIENT_PERMISSIONS, status_code=403, detail="Authentication required.")
    if user.is_superuser:
        return
    lowered = permission_key.lower()
    if has_role(user, ROLE_SAAS_ADMINISTRATOR):
        return
    if has_role(user, ROLE_SAAS_ACCOUNT_MANAGER):
        assigned = get_assigned_account_ids(user)
        if organization.account_id in assigned:
            return
        raise CustomError(code=INSUFFICIENT_PERMISSIONS, status_code=403, detail="Insufficient permissions.")
    # Enable/disable are SaaS-only
    if lowered in {"tools:enable", "tools:disable"}:
        raise CustomError(code=INSUFFICIENT_PERMISSIONS, status_code=403, detail="Insufficient permissions.")
    permissions = {perm.lower() for perm in resolve_effective_permission_keys(user, organization.id)}
    if lowered in permissions or "tools:admin" in permissions:
        return
    raise CustomError(code=INSUFFICIENT_PERMISSIONS, status_code=403, detail="Insufficient permissions.")


def _with_linear_retry(func, attempts=3, base_delay=0.5):
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except Exception as exc:  # noqa: PERF203
            last_exc = exc
            if attempt >= attempts:
                break
            time.sleep(base_delay * attempt)
    if last_exc:
        raise last_exc


def _audit_tool_action(*, user, organization, tool_key: str, action: str, success: bool = True, status_code: int = 200):
    try:
        ctx = get_audit_context()
        trace_id = ctx.trace_id
        span_id = ctx.span_id
        request = getattr(ctx, "request", None)
        ip_addr = get_client_ip(request) if request else None
        user_agent = get_user_agent(request) if request else None
        path = f"/tools/organizations/{organization.uuid}/{tool_key}/{action}"
        AuditLog.objects.create(
            user=user if getattr(user, "is_authenticated", False) else None,
            method="POST",
            path=path[:512],
            view="apps.tools.services",
            app_label="tools",
            model="OrganizationEnabledTool",
            action=action[:31],
            object_id=f"{organization.uuid}:{tool_key}"[:64],
            status_code=status_code,
            success=success,
            ip_addr=ip_addr,
            user_agent=user_agent,
            trace_id=trace_id,
            span_id=span_id,
            extra={"organization_uuid": str(organization.uuid), "tool_key": tool_key},
        )
    except Exception:
        return


def enable_tool(organization, tool_key: str, actor):
    definition = get_tool_definition(tool_key)
    if not definition:
        raise CustomError(code=TOOL_NOT_FOUND, status_code=404, detail="Unknown tool key.")
    existing = OrganizationEnabledTool.objects.filter(
        organization=organization,
        tool_key=tool_key,
        disabled_at__isnull=True,
    ).first()
    if existing:
        return existing
    enforce_tool_limit(organization)
    record = _with_linear_retry(
        lambda: enable_tool_for_organization(organization=organization, tool_key=tool_key, actor=actor),
        attempts=3,
        base_delay=0.5,
    )
    inc_tool_enabled()
    _audit_tool_action(user=actor, organization=organization, tool_key=tool_key, action="enable", success=True)
    return record


def disable_tool(organization, tool_key: str, actor):
    record = OrganizationEnabledTool.objects.filter(organization=organization, tool_key=tool_key).first()
    if not record:
        raise CustomError(code=TOOL_NOT_ENABLED, status_code=404, detail="Tool not enabled for organization.")
    if record.disabled_at:
        raise CustomError(code=TOOL_ALREADY_DISABLED, status_code=400, detail="Tool is already disabled.")
    record = _with_linear_retry(
        lambda: disable_tool_for_organization(organization=organization, tool_key=tool_key, actor=actor),
        attempts=3,
        base_delay=0.5,
    )
    inc_tool_disabled()
    _audit_tool_action(user=actor, organization=organization, tool_key=tool_key, action="disable", success=True)
    return record


def validate_tool_configuration(payload: dict, *, organization):
    """Validate a single tool configuration."""

    entry = {
        "toolKey": payload.get("toolKey") or payload.get("tool_key"),
        "configuration": payload.get("configuration") or {},
    }
    try:
        validated = validate_tools_configuration([entry], organization=organization)
    except ValidationError as exc:
        message = str(exc)
        lowered = message.lower()
        if "collection" in lowered and "not exist" in lowered:
            raise CustomError(code=KB_COLLECTION_NOT_FOUND, status_code=400, detail=message) from exc
        if "uuid" in lowered:
            raise CustomError(code=INVALID_UUID_FORMAT, status_code=400, detail=message) from exc
        if "url" in lowered:
            raise CustomError(code=INVALID_URL_FORMAT, status_code=400, detail=message) from exc
        if "duplicate tool" in lowered:
            raise CustomError(code=TOOL_DUPLICATE, status_code=400, detail=message) from exc
        raise CustomError(code=INVALID_CONFIGURATION, status_code=400, detail=message) from exc
    if validated:
        cleaned = validated[0]
        if cleaned["toolKey"] == "kb_retriever":
            collection_id = cleaned["configuration"].get("collection_id")
            if collection_id:
                exists = Collection.objects.filter(uuid=collection_id, organization=organization).exists()
                if not exists:
                    raise CustomError(
                        code=KB_COLLECTION_NOT_FOUND,
                        status_code=400,
                        detail="Referenced collection does not exist.",
                    )
        return cleaned
    return {}
