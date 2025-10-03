from __future__ import annotations

from django.conf import settings


def email_has_allowed_system_domain(email: str) -> bool:
    """Return ``True`` when ``email`` belongs to an allowed system domain."""

    if not email or "@" not in email:
        return False
    domain = email.split("@", 1)[1].lower()
    configured = getattr(settings, "SYSTEM_EMAIL_DOMAINS", {"hudhud.ai"})

    if isinstance(configured, str):
        configured = {item.strip().lower() for item in configured.split(",") if item.strip()}
    else:
        configured = {str(item).lower() for item in configured}

    return domain in configured


def user_has_active_membership(user, organization) -> bool:
    """Return True when the user is an active member of the organization."""

    if not user or not getattr(user, "is_active", False) or organization is None:
        return False
    try:
        from apps.users.models import UserOrganization
    except ModuleNotFoundError:
        return False
    return UserOrganization.objects.filter(
        user=user,
        organization=organization,
        is_active=True,
        deleted_at__isnull=True,
    ).exists()
