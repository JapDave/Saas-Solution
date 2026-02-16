from __future__ import annotations

from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver

from apps.subscriptions.models import Subscription
from django.conf import settings
from apps.subscriptions.services import is_subscription_active
from apps.llms.services import disable_hosted_llms_for_subscription
from apps.roles.constants import ROLE_AGENT_MANAGER, ROLE_PERMISSION_TEMPLATES
from apps.roles.models import Role


@receiver(pre_save, sender=Subscription)
def _ensure_rate_limit_defaults(sender, instance: Subscription, **kwargs):
    """
    Ensure subscription configuration carries auth rate-limit defaults when not provided.
    Keys: rate_limit_login_attempts, rate_limit_window_minutes.
    """
    cfg = instance.configuration or {}
    cfg.setdefault("rate_limit_login_attempts", getattr(settings, "AUTH_LOGIN_RATE_LIMIT_ATTEMPTS", 3))
    cfg.setdefault("rate_limit_window_minutes", getattr(settings, "AUTH_LOGIN_RATE_LIMIT_WINDOW_MINUTES", 10))
    cfg.setdefault("session_duration_hours", getattr(settings, "AUTH_SESSION_DURATION_DEFAULT_HOURS", 24))
    cfg.setdefault("max_concurrent_sessions", getattr(settings, "AUTH_MAX_CONCURRENT_SESSIONS", 5))
    instance.configuration = cfg


@receiver(post_save, sender=Subscription)
def _enforce_llm_hosted_access(sender, instance: Subscription, **kwargs):
    """
    When LLM subscription changes remove hosted access, disable hosted LLMs.
    """
    try:
        module = getattr(instance, "module", None)
        if not module or getattr(module, "key", "") != "LLM_MANAGEMENT":
            return
        config = instance.configuration or {}
        allowed = config.get("llms_enabled_hosted_models")
        if allowed is None:
            allowed = []
        if not is_subscription_active(instance):
            allowed = []
        disable_hosted_llms_for_subscription(
            organization=instance.organization,
            allowed_hosted_models=set(str(k) for k in allowed),
            reason="subscription_change",
        )
    except Exception:
        return


def _normalize_permissions(keys):
    normalized = []
    for key in keys or []:
        if not isinstance(key, str):
            continue
        value = key.strip().lower()
        if not value or value in normalized:
            continue
        normalized.append(value)
    return normalized


@receiver(post_save, sender=Subscription)
def _ensure_predefined_roles(sender, instance: Subscription, **kwargs):
    try:
        module = getattr(instance, "module", None)
        if not module:
            return
        module_key = getattr(module, "key", "")
        if module_key not in {"AGENTS_MANAGEMENT", "TOOLS_MANAGEMENT", "LLM_MANAGEMENT"}:
            return
        if not is_subscription_active(instance):
            return

        organization = instance.organization
        role_names = [ROLE_AGENT_MANAGER]
        for role_name in role_names:
            template_permissions = ROLE_PERMISSION_TEMPLATES.get(role_name, ())
            role = Role.all_objects.filter(
                organization=organization,
                name=role_name,
            ).first()
            if role:
                updated = False
                if role.deleted_at is not None:
                    role.deleted_at = None
                    updated = True
                if not role.is_active:
                    role.is_active = True
                    updated = True
                if role.role_type != Role.RoleType.PREDEFINED_CUSTOM:
                    role.role_type = Role.RoleType.PREDEFINED_CUSTOM
                    updated = True
                if not role.permissions:
                    role.permissions = _normalize_permissions(template_permissions)
                    updated = True
                if updated:
                    role.save()
            else:
                Role.objects.create(
                    organization=organization,
                    name=role_name,
                    role_type=Role.RoleType.PREDEFINED_CUSTOM,
                    description="Organization role granting agent lifecycle permissions.",
                    permissions=_normalize_permissions(template_permissions),
                    is_active=True,
                    created_by=getattr(organization, "created_by", None),
                )
    except Exception:
        return


@receiver(post_delete, sender=Subscription)
def _enforce_llm_hosted_access_on_delete(sender, instance: Subscription, **kwargs):
    try:
        module = getattr(instance, "module", None)
        if not module or getattr(module, "key", "") != "LLM_MANAGEMENT":
            return
        disable_hosted_llms_for_subscription(
            organization=instance.organization,
            allowed_hosted_models=set(),
            reason="subscription_change",
        )
    except Exception:
        return
