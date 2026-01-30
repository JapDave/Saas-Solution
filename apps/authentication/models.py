from __future__ import annotations

import uuid
from datetime import datetime

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel


class AuthSessionQuerySet(models.QuerySet):
    def active(self):
        now = timezone.now()
        return self.filter(
            deleted_at__isnull=True,
            deactivated_at__isnull=True,
            access_expires_at__gt=now,
        )


class AuthSession(BaseModel):
    """Database-backed session for JWT pairs (spec v1.1.0)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="auth_sessions",
        verbose_name=_("User"),
    )
    access_jti = models.CharField(_("Access token JTI"), max_length=64, unique=True)
    refresh_jti = models.CharField(_("Refresh token JTI"), max_length=64, unique=True)
    access_expires_at = models.DateTimeField(_("Access token expires at"))
    ip_address = models.GenericIPAddressField(_("IP address"), null=True, blank=True)
    user_agent = models.CharField(_("User agent"), max_length=500, blank=True, default="")
    last_activity_at = models.DateTimeField(_("Last activity at"), auto_now_add=True)
    deactivated_at = models.DateTimeField(_("Deactivated at"), null=True, blank=True)
    deactivated_reason = models.CharField(_("Deactivated reason"), max_length=128, blank=True, default="")

    objects = AuthSessionQuerySet.as_manager()
    all_objects = models.Manager()

    class Meta:
        indexes = [
            models.Index(fields=["user_id", "created_at"]),
            models.Index(fields=["access_jti"]),
            models.Index(fields=["refresh_jti"]),
        ]
        ordering = ["-created_at"]

    def touch(self, *, commit: bool = True) -> None:
        self.last_activity_at = timezone.now()
        if commit:
            self.save(update_fields=["last_activity_at", "updated_at"])

    def deactivate(self, *, reason: str = "") -> None:
        if self.deactivated_at:
            return
        self.deactivated_at = timezone.now()
        self.deactivated_reason = reason[:128]
        self.save(update_fields=["deactivated_at", "deactivated_reason", "updated_at"])

    @property
    def is_active_session(self) -> bool:
        now = timezone.now()
        return (
            self.deactivated_at is None
            and self.deleted_at is None
            and self.access_expires_at > now
        )

    def mark_new_access(self, *, access_jti: str, access_expires_at: datetime) -> None:
        self.access_jti = access_jti
        self.access_expires_at = access_expires_at
        self.touch(commit=False)
        self.save(update_fields=["access_jti", "access_expires_at", "last_activity_at", "updated_at"])
