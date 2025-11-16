from __future__ import annotations

from dataclasses import dataclass

from apps.agents.definitions import get_tool_definition, list_tool_definitions
from apps.agents.services import enable_tool_for_organization, disable_tool_for_organization
from apps.agents.validators import validate_tools_configuration
from apps.agents.models import OrganizationEnabledTool
from apps.common.exceptions import (
    CustomError,
    INSUFFICIENT_PERMISSIONS,
    SUBSCRIPTION_LIMIT_EXCEEDED,
    TOOL_NOT_FOUND,
)
from apps.knowledge_base.models import Collection
from apps.subscriptions.services import get_subscription_configuration
from apps.users.services import resolve_effective_permission_keys

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
    permissions = {perm.lower() for perm in resolve_effective_permission_keys(user, organization.id)}
    if permission_key.lower() in permissions or "tools:admin" in permissions:
        return
    raise CustomError(code=INSUFFICIENT_PERMISSIONS, status_code=403, detail="Insufficient permissions.")


def enable_tool(organization, tool_key: str, actor):
    definition = get_tool_definition(tool_key)
    if not definition:
        raise CustomError(code=TOOL_NOT_FOUND, status_code=404, detail="Unknown tool key.")
    enforce_tool_limit(organization)
    record = enable_tool_for_organization(organization=organization, tool_key=tool_key, actor=actor)
    return record


def disable_tool(organization, tool_key: str, actor):
    return disable_tool_for_organization(organization=organization, tool_key=tool_key, actor=actor)


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

