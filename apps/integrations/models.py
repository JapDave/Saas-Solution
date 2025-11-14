from __future__ import annotations

import secrets
import uuid
from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel
from apps.integrations.validators import validate_api_integration, validate_webhook_integration


class IntegrationQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def for_organization(self, organization):
        org_id = getattr(organization, "id", organization)
        return self.filter(organization_id=org_id)


class IntegrationManager(models.Manager.from_queryset(IntegrationQuerySet)):
    def get_queryset(self):
        return super().get_queryset().alive()


class Integration(BaseModel):
    class IntegrationType(models.TextChoices):
        API = "api", _("API")
        WEBHOOK = "webhook", _("Webhook")

    class IntegrationState(models.TextChoices):
        ACTIVE = "active", _("Active")
        INACTIVE = "inactive", _("Inactive")
        DELETED = "deleted", _("Deleted")

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="integrations",
        verbose_name=_("Organization"),
    )
    integration_type = models.CharField(
        _("Integration type"),
        max_length=20,
        choices=IntegrationType.choices,
    )
    name = models.CharField(_("Name"), max_length=250)
    description = models.CharField(_("Description"), max_length=1000, blank=True, default="")
    state = models.CharField(
        _("State"),
        max_length=20,
        choices=IntegrationState.choices,
        default=IntegrationState.ACTIVE,
    )
    is_active = models.BooleanField(_("Is active"), default=True)

    # API integration fields
    url = models.URLField(_("API URL"), max_length=500, blank=True, default="")
    method = models.CharField(_("HTTP method"), max_length=8, blank=True, default="")
    headers = models.JSONField(_("Headers"), default=list, blank=True)
    parameters = models.JSONField(_("Parameters"), default=list, blank=True)
    request_body = models.TextField(_("Request body template"), blank=True, default="")

    # Shared response mappings
    response_mappings = models.JSONField(_("Response mappings"), default=list)

    # Webhook fields
    webhook_url = models.CharField(_("Webhook URL"), max_length=500, blank=True, default="")
    webhook_token = models.CharField(_("Webhook token"), max_length=64, blank=True, default="")
    webhook_secret = models.CharField(_("Webhook secret"), max_length=128, blank=True, default="")
    webhook_sample_payload = models.JSONField(_("Webhook sample payload"), default=dict, blank=True)

    # Invocation metadata
    invocation_count_month = models.PositiveIntegerField(_("Invocations this month"), default=0)
    invocation_count_total = models.PositiveIntegerField(_("Total invocations"), default=0)
    invocation_month = models.DateField(_("Invocation month"), null=True, blank=True)
    last_invocation_at = models.DateTimeField(_("Last invocation at"), null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="integrations_created",
        verbose_name=_("Created by"),
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="integrations_updated",
        verbose_name=_("Updated by"),
    )

    objects = IntegrationManager()
    all_objects = models.Manager()

    class Meta:
        indexes = [
            models.Index(fields=["organization", "integration_type"], name="ix_integration_org_type"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                condition=Q(deleted_at__isnull=True),
                name="uq_integration_name_per_org",
            )
        ]

    def clean(self):
        super().clean()
        if self.name:
            self.name = self.name.strip()
        if not self.name:
            raise ValidationError({"name": _("Name is required.")})
        if self.description is not None:
            self.description = (self.description or "").strip()
            if len(self.description) > 1000:
                raise ValidationError({"description": _("Description must be 1000 characters or fewer.")})
        if self.integration_type == self.IntegrationType.API:
            config = validate_api_integration(
                {
                    "url": self.url,
                    "method": self.method,
                    "headers": self.headers,
                    "parameters": self.parameters,
                    "request_body": self.request_body,
                    "response_mappings": self.response_mappings,
                }
            )
            self.url = config["url"]
            self.method = config["method"]
            self.headers = config["headers"]
            self.parameters = config["parameters"]
            self.request_body = config["request_body"]
            self.response_mappings = config["response_mappings"]
            self.webhook_url = ""
            self.webhook_token = ""
        elif self.integration_type == self.IntegrationType.WEBHOOK:
            config = validate_webhook_integration(
                {
                    "response_mappings": self.response_mappings,
                    "sample_payload": self.webhook_sample_payload,
                }
            )
            self.response_mappings = config["response_mappings"]
            self.webhook_sample_payload = config["sample_payload"]
            self.url = ""
            self.method = ""
            self.headers = []
            self.parameters = []
            self.request_body = ""
        else:
            raise ValidationError({"integration_type": _("Invalid integration type.")})

    def mark_deleted(self):
        if self.state == self.IntegrationState.DELETED:
            return
        self.state = self.IntegrationState.DELETED
        self.is_active = False
        self.deleted_at = timezone.now()
        self.save(update_fields=["state", "is_active", "deleted_at", "updated_at"])

    def delete(self, using=None, keep_parents=False):
        self.mark_deleted()

    def ensure_month_rollover(self):
        today = date.today().replace(day=1)
        if self.invocation_month != today:
            self.invocation_month = today
            self.invocation_count_month = 0

    def increment_invocations(self, count: int = 1):
        self.ensure_month_rollover()
        self.invocation_count_month += max(count, 0)
        self.invocation_count_total += max(count, 0)
        self.last_invocation_at = timezone.now()
        self.save(update_fields=["invocation_count_month", "invocation_count_total", "last_invocation_at", "invocation_month", "updated_at"])

    def regenerate_webhook_credentials(self):
        self.webhook_token = secrets.token_urlsafe(16)
        self.webhook_secret = f"whsec_{secrets.token_urlsafe(24)}"
        if not self.webhook_url:
            self.webhook_url = f"/webhooks/{self.uuid}/{uuid.uuid4().hex}"

    def __str__(self):
        return f"{self.name} ({self.integration_type})"

