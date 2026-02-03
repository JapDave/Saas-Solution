from __future__ import annotations

from dataclasses import dataclass
import time

from apps.agents.definitions import get_tool_definition, list_tool_definitions
from apps.agents.services import enable_tool_for_organization, disable_tool_for_organization
from apps.agents.validators import validate_tools_configuration
from apps.agents.models import OrganizationEnabledTool, Agent
from apps.common.exceptions import (
    CustomError,
    INSUFFICIENT_PERMISSIONS,
    SUBSCRIPTION_LIMIT_EXCEEDED,
    TOOL_NOT_FOUND,
)
from apps.knowledge_base.models import Collection
from apps.subscriptions.services import get_subscription_configuration
from apps.users.services import resolve_effective_permission_keys
from apps.roles.constants import ROLE_SAAS_ADMINISTRATOR, ROLE_SAAS_ACCOUNT_MANAGER, ROLE_ACCOUNT_ADMINISTRATOR
from apps.roles.utils import has_role
from apps.users.models import Membership
from apps.common.models import AuditLog
from apps.common.audit import get_audit_context, get_client_ip, get_user_agent
from apps.tools.telemetry import (
    inc_tool_enabled,
    inc_tool_disabled,
)
from apps.tools.usage import agents_usage_by_tool_keys

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
            code=SUBSCRIPTION_LIMIT_EXCEEDED,
            status_code=409,
            detail=f"{count}/{limits.max_enabled} tools enabled.",
        )


def ensure_tool_permission(user, organization, permission_key: str):
    if not user or not getattr(user, "is_authenticated", False):
        raise CustomError(code=INSUFFICIENT_PERMISSIONS, status_code=403, detail="Authentication required.")
    if user.is_superuser:
        return
    # SaaS-level overrides
    if has_role(user, ROLE_SAAS_ADMINISTRATOR) or has_role(user, ROLE_SAAS_ACCOUNT_MANAGER):
        return
    # Account Admin (org scope) can enable/disable/read
    if has_role(user, ROLE_ACCOUNT_ADMINISTRATOR, organization.uuid):
        return
    permissions = {perm.lower() for perm in resolve_effective_permission_keys(user, organization.id)}
    lowered = permission_key.lower()
    if lowered in permissions or "tools:admin" in permissions:
        return
    # Enabled list/read should be visible to any org member
    if lowered in {"tools:read", "tools:list"} and Membership.objects.filter(
        user=user, organization=organization, deleted_at__isnull=True
    ).exists():
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
    validated = validate_tools_configuration([entry], organization=organization)
    if validated:
        cleaned = validated[0]
        if cleaned["toolKey"] == "kb_retriever":
            collection_id = cleaned["configuration"].get("collection_id")
            if collection_id:
                exists = Collection.objects.filter(uuid=collection_id, organization=organization).exists()
                if not exists:
                    raise CustomError(
                        code="KB_COLLECTION_NOT_FOUND",
                        status_code=400,
                        detail="Referenced collection does not exist.",
                    )
        return cleaned
    return {}
