from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from django.db import transaction

from apps.common.exceptions import CustomError, INSUFFICIENT_PERMISSIONS, SUBSCRIPTION_LIMIT_EXCEEDED
from apps.integrations.models import Integration
from apps.subscriptions.services import get_subscription_configuration
from apps.users.services import resolve_effective_permission_keys

INTEGRATIONS_MODULE_KEY = "INTEGRATIONS_MANAGEMENT"

IntegrationTypeKey = str

DEFAULTS = {
    "api": {"enabled": False, "maxInstances": 10, "maxInvocationsPerMonth": 10000},
    "webhook": {"enabled": False, "maxInstances": 5, "maxInvocationsPerMonth": 5000},
}


@dataclass(frozen=True)
class IntegrationLimit:
    enabled: bool
    max_instances: int
    max_invocations: int


def resolve_integration_limits(organization) -> Dict[str, IntegrationLimit]:
    config = get_subscription_configuration(organization, INTEGRATIONS_MODULE_KEY) or {}
    limits: Dict[str, IntegrationLimit] = {}
    for key in ("api", "webhook"):
        type_key = f"integrations.{key}"
        merged = DEFAULTS[key].copy()
        merged.update(config.get(type_key, {}))
        limits[key] = IntegrationLimit(
            enabled=bool(merged.get("enabled", False)),
            max_instances=max(int(merged.get("maxInstances", DEFAULTS[key]["maxInstances"])), 0),
            max_invocations=max(int(merged.get("maxInvocationsPerMonth", DEFAULTS[key]["maxInvocationsPerMonth"])), 0),
        )
    return limits


def ensure_integration_type_enabled(organization, integration_type: str):
    limits = resolve_integration_limits(organization)
    limit = limits.get(integration_type)
    if not limit or not limit.enabled:
        raise CustomError(
            code="INTEGRATION_TYPE_DISABLED",
            status_code=400,
            detail=f"{integration_type.capitalize()} integrations are disabled by subscription.",
        )
    return limit


def enforce_integration_limit(organization, integration_type: str):
    limit = ensure_integration_type_enabled(organization, integration_type)
    count = Integration.all_objects.filter(
        organization=organization,
        integration_type=integration_type,
        state__in=[Integration.IntegrationState.ACTIVE, Integration.IntegrationState.INACTIVE],
    ).count()
    if count >= limit.max_instances:
        raise CustomError(
            code=SUBSCRIPTION_LIMIT_EXCEEDED,
            status_code=409,
            detail=f"{count}/{limit.max_instances} instances used for {integration_type} integrations.",
        )


def user_has_integration_permission(user, organization, permission_key: str) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    permissions = {perm.lower() for perm in resolve_effective_permission_keys(user, organization.id)}
    target = (permission_key or "").lower()
    return target in permissions or "integrations:admin" in permissions


def ensure_integration_permission(user, organization, permission_key: str):
    if not user_has_integration_permission(user, organization, permission_key):
        raise CustomError(code=INSUFFICIENT_PERMISSIONS, status_code=403, detail="Insufficient permissions.")


@transaction.atomic
def regenerate_webhook_secret(integration: Integration):
    if integration.integration_type != Integration.IntegrationType.WEBHOOK:
        raise CustomError(code="INVALID_OPERATION", status_code=400, detail="Only webhook integrations can regenerate secrets.")
    integration.regenerate_webhook_credentials()
    integration.save(update_fields=["webhook_token", "webhook_secret", "webhook_url", "updated_at"])
    return integration.webhook_secret


__all__ = [
    "INTEGRATIONS_MODULE_KEY",
    "ensure_integration_permission",
    "enforce_integration_limit",
    "regenerate_webhook_secret",
    "resolve_integration_limits",
    "user_has_integration_permission",
]

