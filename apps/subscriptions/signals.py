from __future__ import annotations

from django.db.models.signals import pre_save
from django.dispatch import receiver

from apps.subscriptions.models import Subscription


@receiver(pre_save, sender=Subscription)
def _ensure_rate_limit_defaults(sender, instance: Subscription, **kwargs):
    """
    Ensure subscription configuration carries auth rate-limit defaults when not provided.
    Keys: rate_limit_login_attempts, rate_limit_window_minutes.
    """
    cfg = instance.configuration or {}
    if "rate_limit_login_attempts" not in cfg:
        cfg["rate_limit_login_attempts"] = 3
    if "rate_limit_window_minutes" not in cfg:
        cfg["rate_limit_window_minutes"] = 10
    instance.configuration = cfg
