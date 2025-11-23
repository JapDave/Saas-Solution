from __future__ import annotations

from typing import Optional, Sequence

from django.utils import timezone

from apps.common.exceptions import (
    CustomError,
    ACCOUNT_HAS_ACTIVE_SUBSCRIPTIONS,
    ORGANIZATION_HAS_ACTIVE_SUBSCRIPTIONS,
)
from apps.subscriptions.models import Subscription

ACTIVE_STATUSES: Sequence[str] = (
    Subscription.Status.ACTIVE,
    Subscription.Status.TRIAL,
)


def is_subscription_active(subscription: Subscription) -> bool:
    """Return True when the subscription should currently be enforced."""

    now = timezone.now()
    if subscription.status not in ACTIVE_STATUSES:
        return False
    if subscription.start_date and subscription.start_date > now:
        return False
    if subscription.end_date and subscription.end_date <= now:
        return False
    if (
        subscription.status == Subscription.Status.TRIAL
        and subscription.trial_end_date
        and subscription.trial_end_date <= now
    ):
        return False
    return True


def get_active_subscription(organization, module_key: Optional[str] = None) -> Optional[Subscription]:
    """Return the most recent active subscription for a module (if any)."""

    qs = Subscription.objects.filter(organization=organization)
    if module_key:
        qs = qs.filter(module__key=module_key)
    for subscription in qs.order_by("-created_at"):
        if is_subscription_active(subscription):
            return subscription
    return None


def organization_active_subscriptions(organization) -> list[Subscription]:
    """Return all active subscriptions for an organization."""

    qs = Subscription.objects.filter(
        organization=organization,
        status__in=ACTIVE_STATUSES,
    )
    return [sub for sub in qs if is_subscription_active(sub)]


def account_active_subscriptions(account) -> list[Subscription]:
    """Return all active subscriptions associated with an account."""

    qs = Subscription.objects.filter(
        organization__account=account,
        status__in=ACTIVE_STATUSES,
    ).select_related("module", "organization")
    return [sub for sub in qs if is_subscription_active(sub)]


def ensure_account_has_no_active_subscriptions(account) -> None:
    """Raise when the account has subscriptions that block destructive actions."""

    active = account_active_subscriptions(account)
    if not active:
        return
    module_names = sorted({sub.module.name for sub in active if sub.module})
    detail = "Account has active subscriptions"
    if module_names:
        detail = f"Account has active subscriptions ({', '.join(module_names)})"
    raise CustomError(code=ACCOUNT_HAS_ACTIVE_SUBSCRIPTIONS, status_code=409, detail=detail)


def ensure_organization_has_no_active_subscriptions(organization) -> None:
    """Raise when the organization has subscriptions that block destructive actions."""

    active = organization_active_subscriptions(organization)
    if not active:
        return
    module_names = sorted({sub.module.name for sub in active if sub.module})
    detail = "Organization has active subscriptions"
    if module_names:
        detail = f"Organization has active subscriptions ({', '.join(module_names)})"
    raise CustomError(code=ORGANIZATION_HAS_ACTIVE_SUBSCRIPTIONS, status_code=409, detail=detail)


def get_subscription_configuration(organization, module_key: str) -> dict:
    """Return configuration for an active subscription (empty dict if none)."""

    subscription = get_active_subscription(organization, module_key=module_key)
    if not subscription:
        return {}
    configuration = subscription.configuration or {}
    if isinstance(configuration, dict):
        return configuration
    return {}


__all__ = [
    "is_subscription_active",
    "get_active_subscription",
    "organization_active_subscriptions",
    "account_active_subscriptions",
    "ensure_account_has_no_active_subscriptions",
    "ensure_organization_has_no_active_subscriptions",
    "get_subscription_configuration",
]
