from __future__ import annotations

from django.db.models.signals import post_save

from apps.roles.constants import ROLE_AGENT_MANAGER, ROLE_PERMISSION_TEMPLATES
from apps.roles.models import Role


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


def ensure_agent_manager_role(sender, instance, created: bool = False, **kwargs) -> None:
    """Ensure the Agent Manager role template exists after org creation."""
    if not created:
        return
    Role.objects.get_or_create(
        name=ROLE_AGENT_MANAGER,
        organization=None,
        defaults={
            "role_type": Role.RoleType.USER,
            "description": "Organization template granting full agent lifecycle permissions.",
            "permissions": _normalize_permissions(ROLE_PERMISSION_TEMPLATES.get(ROLE_AGENT_MANAGER, ())),
            "is_active": True,
        },
    )
