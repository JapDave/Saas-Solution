from __future__ import annotations

from datetime import datetime

from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone

from apps.authentication.models import AuthSession
from apps.subscriptions.models import Subscription
from apps.users.models import User
from apps.users.services import invalidate_user_permission_cache
from apps.users.models import UserOrganization


@receiver(pre_save, sender=User)
def _cache_old_password(sender, instance: User, **kwargs):
    if not instance.pk:
        return
    try:
        instance._old_password = (
            User.objects.filter(pk=instance.pk).values_list("password", flat=True).first()
        )
    except Exception:
        instance._old_password = None


@receiver(post_save, sender=User)
def _invalidate_sessions_on_password_change(sender, instance: User, **kwargs):
    old_pw = getattr(instance, "_old_password", None)
    if old_pw and old_pw != instance.password:
        AuthSession.objects.filter(user=instance, deactivated_at__isnull=True).update(
            deactivated_at=timezone.now(),
            deactivated_reason="password_change",
        )


def _invalidate_perm_cache_for_org(org_id: int | None):
    if not org_id:
        return
    user_ids = list(
        UserOrganization.all_objects.filter(organization_id=org_id).values_list("user_id", flat=True)
    )
    for uid in user_ids:
        invalidate_user_permission_cache(uid, org_id)


@receiver(post_save, sender=Subscription)
def _subscription_changed(sender, instance: Subscription, **kwargs):
    _invalidate_perm_cache_for_org(instance.organization_id)


@receiver(post_delete, sender=Subscription)
def _subscription_deleted(sender, instance: Subscription, **kwargs):
    _invalidate_perm_cache_for_org(instance.organization_id)
