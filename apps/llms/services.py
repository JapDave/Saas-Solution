from __future__ import annotations

from dataclasses import dataclass

from apps.agents.definitions import get_llm_definition, list_llm_definitions
from apps.agents.models import OrganizationEnabledLLM
from apps.agents.services import (
    enable_llm_for_organization,
    disable_llm_for_organization,
    ensure_llm_allowed_for_subscription,
)
from apps.agents.validators import validate_llm_configuration
from apps.common.exceptions import CustomError, INSUFFICIENT_PERMISSIONS, SUBSCRIPTION_LIMIT_EXCEEDED, LLM_NOT_FOUND
from apps.agents.models import Agent
from apps.subscriptions.services import get_subscription_configuration
from apps.users.services import resolve_effective_permission_keys
from apps.roles.constants import ROLE_SAAS_ADMINISTRATOR, ROLE_SAAS_ACCOUNT_MANAGER, ROLE_AGENT_MANAGER
from apps.roles.utils import has_role

LLM_MODULE_KEY = "LLM_MANAGEMENT"


@dataclass(frozen=True)
class LLMLimits:
    max_enabled: int


DEFAULT_LIMITS = LLMLimits(max_enabled=20)


def resolve_llm_limits(organization) -> LLMLimits:
    config = get_subscription_configuration(organization, LLM_MODULE_KEY) or {}
    return LLMLimits(
        max_enabled=int(config.get("llms.max_enabled", DEFAULT_LIMITS.max_enabled)),
    )


def enforce_llm_enable_limit(organization):
    limits = resolve_llm_limits(organization)
    count = OrganizationEnabledLLM.objects.filter(organization=organization, disabled_at__isnull=True).count()
    if count >= limits.max_enabled:
        raise CustomError(
            code=SUBSCRIPTION_LIMIT_EXCEEDED,
            status_code=409,
            detail=f"{count}/{limits.max_enabled} enabled LLMs.",
        )


def ensure_llm_permission(user, organization, permission_key: str):
    if not user or not getattr(user, "is_authenticated", False):
        raise CustomError(code=INSUFFICIENT_PERMISSIONS, status_code=403, detail="Authentication required.")
    if user.is_superuser:
        return
    # System roles: SaaS Admin / SaaS Account Manager can do everything
    if has_role(user, ROLE_SAAS_ADMINISTRATOR):
        return
    if has_role(user, ROLE_SAAS_ACCOUNT_MANAGER):
        return
    # Org role: Agent Manager may list/read enabled LLMs
    if permission_key.lower() in {"llms:read", "llms:list"} and has_role(
        user, ROLE_AGENT_MANAGER, organization.uuid
    ):
        return
    # treat list as read for backward compatibility
    if permission_key.lower() == "llms:list":
        permission_key = "llms:read"
    permissions = {perm.lower() for perm in resolve_effective_permission_keys(user, organization.id)}
    if permission_key.lower() in permissions or "llms:admin" in permissions:
        return
    raise CustomError(code=INSUFFICIENT_PERMISSIONS, status_code=403, detail="Insufficient permissions.")


def enable_llm(organization, model_key: str, actor):
    definition = get_llm_definition(model_key)
    if not definition:
        raise CustomError(code=LLM_NOT_FOUND, status_code=404, detail="Unknown LLM key.")
    # Hosted/hudhud provider guard
    ensure_llm_allowed_for_subscription(organization, model_key)
    enforce_llm_enable_limit(organization)
    record = enable_llm_for_organization(organization=organization, model_key=model_key, actor=actor)
    return record


def disable_llm(organization, model_key: str, actor):
    return disable_llm_for_organization(organization=organization, model_key=model_key, actor=actor)


def validate_configuration(payload: dict, *, organization):
    model_key = payload.get("modelKey")
    definition = get_llm_definition(model_key)
    if not definition:
        raise CustomError(code=LLM_NOT_FOUND, status_code=404, detail="Unknown LLM key.")
    validated = validate_llm_configuration(payload, organization=organization)
    return validated


def agents_usage_by_model_keys(org, model_keys: list[str]) -> dict[str, int]:
    """
    Count agents within an org using each modelKey (by llm_configuration.modelKey).
    """
    if not model_keys:
        return {}
    qs = (
        Agent.objects.filter(
            organization=org,
            llm_configuration__modelKey__in=model_keys,
            deleted_at__isnull=True,
        )
        .values_list("llm_configuration__modelKey", flat=True)
    )
    usage: dict[str, int] = {}
    for key in qs:
        usage[key] = usage.get(key, 0) + 1
    return usage
