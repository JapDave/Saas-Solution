from __future__ import annotations

from django.db.models.signals import pre_save
from django.dispatch import receiver

from apps.subscriptions.models import Subscription
from django.conf import settings


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
