# std lib
import uuid

# Django/DRF imports
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

    uuid = models.UUIDField(_("UUID"), default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="subscriptions",
        verbose_name=_("Organization")
    )
    module = models.ForeignKey(
        "products.Module",
        on_delete=models.CASCADE,
        related_name="subscriptions",
        verbose_name=_("Module")
    )
    status = models.CharField(
        _("Status"),
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    configuration = models.JSONField(_("Configuration"), default=dict)

    start_date = models.DateTimeField(_("Start date"))
    end_date = models.DateTimeField(_("End date"), null=True, blank=True)
    trial_end_date = models.DateTimeField(_("Trial end date"), null=True, blank=True)

    class Meta:
        verbose_name = _("Subscription")
        verbose_name_plural = _("Subscriptions")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.organization} - {self.module.name} ({self.get_status_display()})"
