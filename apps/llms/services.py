from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable, Type, Sequence

from apps.agents.definitions import get_llm_definition, list_llm_definitions
from apps.agents.models import OrganizationEnabledLLM
from apps.agents.services import (
    enable_llm_for_organization,
    disable_llm_for_organization,
    ensure_llm_allowed_for_subscription,
)
from apps.agents.validators import validate_llm_configuration
from apps.common.exceptions import (
    CustomError,
    INSUFFICIENT_PERMISSIONS,
    MAX_LLMS_EXCEEDED,
    LLM_NOT_FOUND,
    SUBSCRIPTION_REQUIRED,
    INVALID_CONFIGURATION,
)
from apps.agents.models import Agent
from apps.subscriptions.services import get_subscription_configuration
from apps.users.services import resolve_effective_permission_keys
from apps.roles.constants import (
    ROLE_SAAS_ADMINISTRATOR,
    ROLE_SAAS_ACCOUNT_MANAGER,
    ROLE_ACCOUNT_ADMINISTRATOR,
    ROLE_ACCOUNT_OWNER,
    ROLE_ORGANIZATION_ADMINISTRATOR,
    ROLE_ORGANIZATION_OWNER,
)
from apps.roles.utils import has_role
from apps.common.models import AuditLog
from apps.common.audit import get_audit_context, get_client_ip, get_user_agent
from apps.llms.telemetry import inc_llm_enabled, inc_llm_disabled
from apps.accounts.services import get_assigned_account_ids
from django.contrib.auth import get_user_model
from django.conf import settings
from apps.subscriptions.services import get_active_subscription
from apps.accounts.models import Account

LLM_MODULE_KEY = "LLM_MANAGEMENT"


@dataclass(frozen=True)
class LLMLimits:
    max_enabled: int



DEFAULT_LIMITS = LLMLimits(max_enabled=20)


def resolve_llm_limits(organization) -> LLMLimits:
    config = get_subscription_configuration(organization, LLM_MODULE_KEY) or {}
    max_enabled = (
        config.get("llms_max_enabled_per_org")
        if config.get("llms_max_enabled_per_org") is not None
        else config.get("llms.max_enabled")
    )
    return LLMLimits(
        max_enabled=int(max_enabled or DEFAULT_LIMITS.max_enabled),
    )


def enforce_llm_enable_limit(organization):
    limits = resolve_llm_limits(organization)
    count = OrganizationEnabledLLM.objects.filter(organization=organization, disabled_at__isnull=True).count()
    if count >= limits.max_enabled:
        raise CustomError(
            code=MAX_LLMS_EXCEEDED,
            status_code=409,
            detail=f"{count}/{limits.max_enabled} enabled LLMs.",
        )


def ensure_llm_permission(user, organization, permission_key: str):
    if not user or not getattr(user, "is_authenticated", False):
        raise CustomError(code=INSUFFICIENT_PERMISSIONS, status_code=403, detail="Authentication required.")
    if user.is_superuser:
        return
    lowered_key = (permission_key or "").lower()
    # List/enable/disable are restricted to SaaS roles only.
    if lowered_key in {"llms:list", "llms:enable", "llms:disable"}:
        if has_role(user, ROLE_SAAS_ADMINISTRATOR):
            return
        if has_role(user, ROLE_SAAS_ACCOUNT_MANAGER):
            assigned = get_assigned_account_ids(user)
            if not assigned or organization.account_id in assigned:
                return
        raise CustomError(code=INSUFFICIENT_PERMISSIONS, status_code=403, detail="Insufficient permissions.")
    if lowered_key == "llms:read":
        if has_role(user, ROLE_SAAS_ADMINISTRATOR):
            return
        if has_role(user, ROLE_SAAS_ACCOUNT_MANAGER):
            assigned = get_assigned_account_ids(user)
            if not assigned or organization.account_id in assigned:
                return
        if has_role(user, ROLE_ACCOUNT_OWNER, organization.uuid):
            return
        if has_role(user, ROLE_ACCOUNT_ADMINISTRATOR, organization.uuid):
            return
        if has_role(user, ROLE_ORGANIZATION_OWNER, organization.uuid):
            return
        if has_role(user, ROLE_ORGANIZATION_ADMINISTRATOR, organization.uuid):
            return
        permissions = {perm.lower() for perm in resolve_effective_permission_keys(user, organization.id)}
        if lowered_key in permissions or "llms:admin" in permissions:
            return
        raise CustomError(code=INSUFFICIENT_PERMISSIONS, status_code=403, detail="Insufficient permissions.")
    # System roles: SaaS Admin / SaaS Account Manager can do everything
    if has_role(user, ROLE_SAAS_ADMINISTRATOR):
        return
    if has_role(user, ROLE_SAAS_ACCOUNT_MANAGER):
        # SaaS Account Managers are scoped to assigned accounts
        assigned = get_assigned_account_ids(user)
        if not assigned or organization.account_id in assigned:
            return
        return
    # Ownership-based access without role assignment.
    if getattr(organization, "created_by_id", None) == getattr(user, "id", None):
        return
    if Account.objects.filter(id=organization.account_id, created_by_id=getattr(user, "id", None)).exists():
        return
    # Static org roles should grant access within their assigned organization.
    if has_role(user, ROLE_ACCOUNT_OWNER, organization.uuid):
        return
    if has_role(user, ROLE_ACCOUNT_ADMINISTRATOR, organization.uuid):
        return
    if has_role(user, ROLE_ORGANIZATION_OWNER, organization.uuid):
        return
    if has_role(user, ROLE_ORGANIZATION_ADMINISTRATOR, organization.uuid):
        return
    permissions = {perm.lower() for perm in resolve_effective_permission_keys(user, organization.id)}
    if permission_key.lower() in permissions or "llms:admin" in permissions:
        return
    raise CustomError(code=INSUFFICIENT_PERMISSIONS, status_code=403, detail="Insufficient permissions.")


def ensure_llm_subscription(organization):
    subscription = get_active_subscription(organization, module_key=LLM_MODULE_KEY)
    if not subscription:
        raise CustomError(
            code=SUBSCRIPTION_REQUIRED,
            status_code=403,
            detail="LLM subscription required for this organization.",
        )


def _system_user():
    user_model = get_user_model()
    email = getattr(settings, "AUDIT_SYSTEM_USER_EMAIL", "") or ""
    if not email:
        return user_model.objects.filter(is_superuser=True).order_by("id").first()
    try:
        user = user_model.objects.filter(email=email).first()
        if user:
            return user
        return user_model.objects.create_user(email=email, password=None, is_active=True)
    except Exception:
        return None


def _with_linear_retry(func: Callable, *, attempts: int = 3, base_delay: float = 0.5, retry_exceptions: Sequence[Type[BaseException]] = (Exception,)):
    """
    Execute `func` with linear backoff retries.
    attempts: total attempts (including first); spec wants 2 retries => attempts=3.
    base_delay: initial sleep in seconds; second retry waits base_delay * 2.
    """
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except retry_exceptions as exc:  # noqa: PERF203
            last_exc = exc
            if attempt >= attempts:
                break
            # linear backoff: base, 2*base
            time.sleep(base_delay * attempt)
    if last_exc:
        raise last_exc
    return None


def _audit_llm_action(*, user, organization, model_key: str, action: str, success: bool = True, reason: str | None = None, status_code: int = 200):
    """Write an AuditLog entry for LLM enable/disable events without interrupting the main flow."""
    try:
        ctx = get_audit_context()
        trace_id = ctx.trace_id
        span_id = ctx.span_id
        request = getattr(ctx, "request", None)
        ip_addr = get_client_ip(request) if request else None
        user_agent = get_user_agent(request) if request else None
        path = f"/llms/organizations/{organization.uuid}/{model_key}/{action}"
        AuditLog.objects.create(
            user=user if getattr(user, "is_authenticated", False) else None,
            method="POST",
            path=path[:512],
            view="apps.llms.services",
            app_label="llms",
            model="OrganizationEnabledLLM",
            action=action[:31],
            object_id=f"{organization.uuid}:{model_key}"[:64],
            status_code=status_code,
            success=success,
            ip_addr=ip_addr,
            user_agent=user_agent,
            trace_id=trace_id,
            span_id=span_id,
            extra={"organization_uuid": str(organization.uuid), "model_key": model_key, "reason": reason},
        )
    except Exception:
        return


def enable_llm(organization, model_key: str, actor):
    definition = get_llm_definition(model_key)
    if not definition:
        raise CustomError(code=LLM_NOT_FOUND, status_code=404, detail="Unknown LLM key.")
    # Hosted/hudhud provider guard
    ensure_llm_allowed_for_subscription(organization, model_key)
    enforce_llm_enable_limit(organization)
    record = _with_linear_retry(
        lambda: enable_llm_for_organization(organization=organization, model_key=model_key, actor=actor),
        attempts=3,
        base_delay=0.5,
    )
    _audit_llm_action(user=actor, organization=organization, model_key=model_key, action="enable", success=True)
    inc_llm_enabled(hosted=definition.requires_hosted_subscription)
    return record


def disable_llm(organization, model_key: str, actor):
    record = _with_linear_retry(
        lambda: disable_llm_for_organization(organization=organization, model_key=model_key, actor=actor),
        attempts=3,
        base_delay=0.5,
    )
    _audit_llm_action(user=actor, organization=organization, model_key=model_key, action="disable", success=True)
    inc_llm_disabled()
    return record


def validate_configuration(payload: dict, *, organization):
    model_key = payload.get("modelKey")
    definition = get_llm_definition(model_key)
    if not definition:
        raise CustomError(code=LLM_NOT_FOUND, status_code=404, detail="Unknown LLM key.")
    try:
        validated = validate_llm_configuration(payload, organization=organization)
        return validated
    except Exception as exc:
        raise CustomError(code=INVALID_CONFIGURATION, status_code=400, detail=str(exc)) from exc


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


def disable_hosted_llms_for_subscription(*, organization, allowed_hosted_models: set[str] | None, reason: str = "subscription_change"):
    """
    Disable any hosted LLMs that are enabled but no longer allowed by subscription.
    """
    hosted_keys = {d.key for d in list_llm_definitions() if d.requires_hosted_subscription}
    if allowed_hosted_models is None:
        allowed_hosted_models = set()
    to_disable = hosted_keys - set(allowed_hosted_models)
    if not to_disable:
        return
    records = OrganizationEnabledLLM.objects.filter(
        organization=organization,
        disabled_at__isnull=True,
        model_key__in=to_disable,
    )
    if not records.exists():
        return
    actor = _system_user()
    for record in records:
        record.disable(actor=actor)
        _audit_llm_action(
            user=actor,
            organization=organization,
            model_key=record.model_key,
            action="disable",
            success=True,
            reason=reason,
        )
