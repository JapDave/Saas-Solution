# std lib
import uuid

# Django/DRF imports
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

# Project imports
from apps.common.models import BaseModel

class Subscription(BaseModel):
    """
    Represents a subscription of an organization to a specific module.
    """
    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        EXPIRED = "expired", _("Expired")
        SUSPENDED = "suspended", _("Suspended")
        CANCELLED = "cancelled", _("Cancelled")
        TRIAL = "trial", _("Trial")
        ARCHIVED = "archived", _("Archived")

    uuid = models.UUIDField(default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="subscriptions"
    )
    module = models.ForeignKey(
        "products.Module",
        on_delete=models.CASCADE,
        related_name="subscriptions"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    configuration = models.JSONField(default=dict)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_subscriptions",
        null=True,
        blank=False,
    )
    start_date = models.DateTimeField()
    end_date = models.DateTimeField(null=True, blank=True)
    trial_end_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("Subscription")
        verbose_name_plural = _("Subscriptions")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.organization} - {self.module.name} ({self.get_status_display()})"
