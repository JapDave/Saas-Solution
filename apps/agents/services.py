from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Iterable, Optional, Set

from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from apps.agents.definitions import get_llm_definition, get_tool_definition
from apps.agents.models import (
    Agent,
    AgentVersion,
    OrganizationEnabledLLM,
    OrganizationEnabledTool,
)
from apps.agents.validators import (
    validate_agent_description,
    validate_agent_name,
    validate_llm_configuration,
    validate_system_prompts,
    validate_tools_configuration,
)
from apps.accounts.services import get_assigned_account_ids
from apps.agents.telemetry import inc_subscription_check_failures
from apps.common.exceptions import (
    AGENT_NAME_NOT_UNIQUE,
    CustomError,
    InsufficientPermissions,
    INVALID_AGENT_DATA,
    INVALID_LLM_CONFIGURATION,
    INVALID_TOOL_CONFIGURATION,
    LLM_NOT_ENABLED,
    LLM_NOT_FOUND,
    LLM_ALREADY_DISABLED,
    LLM_NOT_PERMITTED,
    LLM_REQUIRED,
    SUBSCRIPTION_LIMIT_EXCEEDED,
    SUBSCRIPTION_REQUIRED,
    TOOL_ALREADY_DISABLED,
    TOOL_NOT_ENABLED,
    TOOL_NOT_FOUND,
)
from apps.subscriptions.services import get_active_subscription, get_subscription_configuration
from apps.users.services import (
    get_user_accessible_account_ids,
    get_user_accessible_organization_ids,
    resolve_effective_permission_keys,
)

AGENTS_MODULE_KEY = "AGENTS_MANAGEMENT"


@dataclass(frozen=True)
class AgentLimits:
    max_agents: Optional[int]
    enabled_hosted_llms: set[str]
    tool_invocations_per_month: Optional[int]


DEFAULT_LIMITS = AgentLimits(
    max_agents=10,
    enabled_hosted_llms=set(),
    tool_invocations_per_month=1000,
)


def _coerce_positive(value) -> Optional[int]:
    if value in (None, "", 0):
        return None
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return None
    return numeric if numeric > 0 else None


def resolve_agent_limits(organization) -> AgentLimits:
    config = get_subscription_configuration(organization, AGENTS_MODULE_KEY) or {}
    enabled_hosted = config.get("agents_enabled_hosted_llms") or []
    return AgentLimits(
        max_agents=_coerce_positive(config.get("agents_max_agents_per_org")) or DEFAULT_LIMITS.max_agents,
        enabled_hosted_llms={str(key) for key in enabled_hosted if isinstance(key, str)},
        tool_invocations_per_month=_coerce_positive(config.get("agents_tool_invocations_per_month"))
        or DEFAULT_LIMITS.tool_invocations_per_month,
    )


def enforce_agent_creation_limit(organization):
    limits = resolve_agent_limits(organization)
    if limits.max_agents is None:
        return
    current = Agent.objects.filter(organization=organization).count()
    if current >= limits.max_agents:
        raise CustomError(
            code=SUBSCRIPTION_LIMIT_EXCEEDED,
            status_code=409,
            detail="Organization has reached its agent limit.",
        )


def ensure_agent_name_unique(*, organization, name: str, exclude_agent: Agent | None = None):
    qs = Agent.all_objects.filter(
        organization=organization,
        name=name,
        deleted_at__isnull=True,
    )
    if exclude_agent is not None:
        qs = qs.exclude(pk=exclude_agent.pk)
    if qs.exists():
        raise CustomError(
            code=AGENT_NAME_NOT_UNIQUE,
            status_code=409,
            detail="Agent name already exists in organization.",
        )


def ensure_agent_subscription(organization):
    subscription = get_active_subscription(organization, module_key=AGENTS_MODULE_KEY)
    if not subscription:
        inc_subscription_check_failures()
        raise CustomError(
            code=SUBSCRIPTION_REQUIRED,
            status_code=403,
            detail="Active AGENTS_MANAGEMENT subscription required.",
        )


def ensure_llm_allowed_for_subscription(organization, model_key: str):
    definition = get_llm_definition(model_key)
    if not definition or not definition.requires_hosted_subscription:
        return
    llm_config = get_subscription_configuration(organization, "LLM_MANAGEMENT") or {}
    hosted_allowed = llm_config.get("llms_enabled_hosted_models")
    if hosted_allowed is None:
        limits = resolve_agent_limits(organization)
        hosted_allowed = list(limits.enabled_hosted_llms)
    if model_key not in set(str(k) for k in (hosted_allowed or [])):
        raise CustomError(
            code=LLM_NOT_PERMITTED,
            status_code=403,
            detail=f"{model_key} is not allowed by subscription.",
        )


def next_version_number(agent: Agent) -> int:
    latest = agent.versions.aggregate(max_version=Max("version_number")).get("max_version") or 0
    return latest + 1


def _with_linear_retry(func, *, attempts: int = 3, base_delay: float = 0.5):
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
    return None


def _normalize_tools(tools: Iterable[dict]) -> list[dict]:
    if isinstance(tools, dict) and "tools" in tools:
        tools = tools.get("tools") or []
    normalized = []
    for entry in tools or []:
        if not isinstance(entry, dict):
            continue
        key = entry.get("toolKey") or entry.get("tool_key")
        config = entry.get("configuration") or {}
        normalized.append({"toolKey": key, "configuration": config})
    return sorted(normalized, key=lambda item: item.get("toolKey") or "")


@transaction.atomic
def save_agent_version(
    agent: Agent,
    *,
    actor,
    name: str | None = None,
    description: str | None = None,
    system_prompts: str | None = None,
    llm_configuration: dict | None = None,
    tools_configuration: list | dict | None = None,
) -> tuple[AgentVersion, bool]:
    candidate_name = validate_agent_name(name if name is not None else agent.name)
    candidate_description = validate_agent_description(
        description if description is not None else agent.description
    )

    if system_prompts is None:
        system_prompts = agent.system_prompts
    if not system_prompts:
        raise CustomError(code=INVALID_AGENT_DATA, status_code=400, detail="systemPrompts is required.")
    try:
        system_prompts = validate_system_prompts(system_prompts)
    except Exception as exc:
        raise CustomError(code=INVALID_AGENT_DATA, status_code=400, detail=str(exc)) from exc

    if llm_configuration is None:
        llm_configuration = agent.llm_configuration
    if not llm_configuration:
        raise CustomError(code=LLM_REQUIRED, status_code=400, detail="Agent must have exactly one LLM configured.")
    if not get_active_subscription(agent.organization, module_key="LLM_MANAGEMENT"):
        raise CustomError(
            code=SUBSCRIPTION_REQUIRED,
            status_code=403,
            detail="Active LLM_MANAGEMENT subscription required.",
        )

    try:
        sanitized_llm = validate_llm_configuration(
            llm_configuration or {},
            organization=agent.organization,
            raise_custom_error=True,
        )
    except CustomError:
        raise
    except Exception as exc:
        raise CustomError(code=INVALID_LLM_CONFIGURATION, status_code=400, detail=str(exc)) from exc

    if tools_configuration is None:
        tools_configuration = agent.tools_configuration
    if isinstance(tools_configuration, dict) and "tools" in tools_configuration:
        tools_configuration = tools_configuration.get("tools") or []
    if tools_configuration:
        if not get_active_subscription(agent.organization, module_key="TOOLS_MANAGEMENT"):
            raise CustomError(
                code=SUBSCRIPTION_REQUIRED,
                status_code=403,
                detail="Active TOOLS_MANAGEMENT subscription required.",
            )
    try:
        sanitized_tools_list = validate_tools_configuration(
            tools_configuration or [],
            organization=agent.organization,
            raise_custom_error=True,
            allow_incomplete=True,
        )
    except CustomError:
        raise
    except Exception as exc:
        raise CustomError(code=INVALID_TOOL_CONFIGURATION, status_code=400, detail=str(exc)) from exc
    sanitized_tools = {"tools": sanitized_tools_list}

    latest = agent.versions.order_by("-version_number").first()
    if latest:
        same = (
            latest.name == candidate_name
            and latest.description == candidate_description
            and latest.system_prompts == system_prompts
            and latest.llm_configuration == sanitized_llm
            and _normalize_tools(latest.tools_configuration) == _normalize_tools(sanitized_tools)
        )
        if same:
            if agent.current_version_id != latest.id:
                agent.current_version = latest
                agent.updated_by = actor
                agent.save(update_fields=["current_version", "updated_by", "updated_at"])
            return latest, False

    def _create_version():
        version = AgentVersion.objects.create(
            agent=agent,
            version_number=next_version_number(agent),
            name=candidate_name,
            description=candidate_description,
            system_prompts=system_prompts,
            llm_configuration=sanitized_llm,
            tools_configuration=sanitized_tools,
            created_by=actor,
        )
        return version

    version = _with_linear_retry(_create_version, attempts=3, base_delay=0.5)

    agent.name = candidate_name
    agent.description = candidate_description
    agent.system_prompts = system_prompts
    agent.llm_configuration = sanitized_llm
    agent.tools_configuration = sanitized_tools
    agent.current_version = version
    agent.updated_by = actor
    agent.save(update_fields=[
        "name",
        "description",
        "system_prompts",
        "llm_configuration",
        "tools_configuration",
        "current_version",
        "updated_by",
        "updated_at",
    ])
    return version, True


def clone_agent(agent: Agent, *, created_by, name_override: str | None = None) -> Agent:
    if name_override:
        candidate = validate_agent_name(name_override)
        ensure_agent_name_unique(organization=agent.organization, name=candidate)
    else:
        base_name = f"Copy of {agent.name}"
        candidate = base_name
        counter = 2
        while Agent.objects.filter(organization=agent.organization, name=candidate).exists():
            candidate = f"{base_name} ({counter})"
            counter += 1

    source_version = agent.current_version or agent.versions.order_by("-version_number").first()
    llm_configuration = source_version.llm_configuration if source_version else agent.llm_configuration
    tools_configuration = source_version.tools_configuration if source_version else agent.tools_configuration
    system_prompts = source_version.system_prompts if source_version else agent.system_prompts
    new_agent = Agent.objects.create(
        organization=agent.organization,
        name=candidate,
        description=agent.description,
        system_prompts=system_prompts,
        llm_configuration=llm_configuration,
        tools_configuration=tools_configuration,
        state=Agent.AgentState.DRAFT,
        created_by=created_by,
        updated_by=created_by,
    )
    if llm_configuration:
        save_agent_version(
            new_agent,
            actor=created_by,
            name=new_agent.name,
            description=new_agent.description,
            system_prompts=system_prompts,
            llm_configuration=llm_configuration,
            tools_configuration=tools_configuration,
        )
    return new_agent


def _is_authenticated(user) -> bool:
    return bool(user and getattr(user, "is_authenticated", False))


def _org_owner_ids(organization) -> Set[int]:
    owner_ids: Set[int] = set()
    created_by_id = getattr(organization, "created_by_id", None)
    account = getattr(organization, "account", None)
    if created_by_id:
        owner_ids.add(created_by_id)
    if account and getattr(account, "created_by_id", None):
        owner_ids.add(account.created_by_id)
    return owner_ids


def filter_agents_for_user(queryset, user):
    if not _is_authenticated(user):
        return queryset.none()
    if user.is_superuser:
        return queryset
    if user.is_staff:
        assigned = get_assigned_account_ids(user)
        if not assigned:
            return queryset
        return queryset.filter(organization__account_id__in=assigned)

    account_ids = get_user_accessible_account_ids(user)
    organization_ids = get_user_accessible_organization_ids(user)
    filters = Q()
    if account_ids:
        filters |= Q(organization__account_id__in=account_ids)
    if organization_ids:
        filters |= Q(organization_id__in=organization_ids)
    if not filters:
        return queryset.none()
    return queryset.filter(filters).distinct()


def _permission_keys(user, organization) -> Set[str]:
    return {
        perm.lower()
        for perm in resolve_effective_permission_keys(user, organization.id)
    }


def user_has_agent_permission(user, organization, permission_key: str) -> bool:
    if not _is_authenticated(user):
        return False
    if user.is_superuser:
        return True
    if user.is_staff:
        assigned = get_assigned_account_ids(user)
        return not assigned or organization.account_id in assigned
    if user.id in _org_owner_ids(organization):
        return True
    perms = _permission_keys(user, organization)
    lowered = permission_key.lower()
    return lowered in perms or "agents:admin" in perms


def ensure_agent_permission(user, organization, permission_key: str):
    if not user_has_agent_permission(user, organization, permission_key):
        raise InsufficientPermissions()


def enable_llm_for_organization(*, organization, model_key: str, actor=None) -> OrganizationEnabledLLM:
    definition = get_llm_definition(model_key)
    if not definition:
        raise CustomError(code=LLM_NOT_FOUND, status_code=404, detail="Unknown LLM key.")
    ensure_llm_allowed_for_subscription(organization, model_key)
    record, _created = OrganizationEnabledLLM.objects.get_or_create(
        organization=organization,
        model_key=model_key,
        defaults={
            "model_provider": definition.provider,
            "display_name": definition.display_name,
            "enabled_by": actor,
        },
    )
    if record.disabled_at:
        record.disabled_at = None
        record.model_provider = definition.provider
        record.display_name = definition.display_name
        record.enabled_by = actor
        record.save(update_fields=["disabled_at", "model_provider", "display_name", "enabled_by", "updated_at"])
    return record


def disable_llm_for_organization(*, organization, model_key: str, actor=None) -> OrganizationEnabledLLM:
    record = OrganizationEnabledLLM.objects.filter(
        organization=organization,
        model_key=model_key,
    ).first()
    if not record:
        raise CustomError(code=LLM_NOT_ENABLED, status_code=404, detail="LLM not enabled for organization.")
    if record.disabled_at:
        raise CustomError(code=LLM_ALREADY_DISABLED, status_code=400, detail="LLM already disabled.")
    record.disable(actor=actor)
    return record


def enable_tool_for_organization(*, organization, tool_key: str, actor=None) -> OrganizationEnabledTool:
    definition = get_tool_definition(tool_key)
    if not definition:
        raise CustomError(code=TOOL_NOT_FOUND, status_code=404, detail="Unknown tool key.")
    record, _ = OrganizationEnabledTool.objects.get_or_create(
        organization=organization,
        tool_key=tool_key,
        defaults={
            "enabled_by": actor,
            "display_name": definition.display_name,
            "category": definition.raw.get("category", ""),
        },
    )
    if record.disabled_at:
        record.disabled_at = None
        record.enabled_by = actor
        record.display_name = definition.display_name
        record.category = definition.raw.get("category", "")
        record.save(update_fields=["disabled_at", "enabled_by", "display_name", "category", "updated_at"])
    else:
        if record.display_name != definition.display_name or record.category != (definition.raw.get("category", "")):
            record.display_name = definition.display_name
            record.category = definition.raw.get("category", "")
            record.save(update_fields=["display_name", "category", "updated_at"])
    return record


def disable_tool_for_organization(*, organization, tool_key: str, actor=None) -> OrganizationEnabledTool:
    record = OrganizationEnabledTool.objects.filter(
        organization=organization,
        tool_key=tool_key,
    ).first()
    if not record:
        raise CustomError(code=TOOL_NOT_ENABLED, status_code=404, detail="Tool not enabled for organization.")
    if record.disabled_at:
        raise CustomError(code=TOOL_ALREADY_DISABLED, status_code=400, detail="Tool is already disabled.")
    record.disable(actor=actor)
    return record
