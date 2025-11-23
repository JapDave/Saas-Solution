from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel
from apps.flows.validators import validate_flow_configurations, validate_flow_json


class FlowQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def for_organization(self, organization):
        org_id = getattr(organization, "id", organization)
        return self.filter(organization_id=org_id)


class FlowManager(models.Manager.from_queryset(FlowQuerySet)):
    def get_queryset(self):
        return super().get_queryset().alive()


class Flow(BaseModel):
    """Container entity representing a workflow with multiple versions."""

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="flows",
        verbose_name=_("Organization"),
    )
    name = models.CharField(_("Name"), max_length=250)
    description = models.CharField(_("Description"), max_length=1000, blank=True, default="")
    flow_configurations = models.JSONField(_("Flow configurations"), default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="flows_created",
        verbose_name=_("Created by"),
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="flows_updated",
        verbose_name=_("Updated by"),
    )

    objects = FlowManager()
    all_objects = models.Manager()

    class Meta:
        indexes = [
            models.Index(fields=["organization", "name"], name="ix_flow_org_name"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="uq_flow_name_per_org",
                condition=Q(deleted_at__isnull=True),
            ),
        ]

    def clean(self):
        super().clean()
        if self.name:
            self.name = self.name.strip()
        if not self.name:
            raise ValidationError({"name": _("Name is required.")})
        if len(self.name) > 250:
            raise ValidationError({"name": _("Name must be 250 characters or fewer.")})
        if self.description is not None:
            self.description = (self.description or "").strip()
            if len(self.description) > 1000:
                raise ValidationError({"description": _("Description must be 1000 characters or fewer.")})
        self.flow_configurations = validate_flow_configurations(self.flow_configurations or {})

    def active_version_for_state(self, state: str):
        return self.versions.filter(state=state, is_active=True).first()

    def __str__(self):
        return f"{self.name} ({self.organization_id})"


class FlowVersionQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def for_state(self, state: str):
        return self.filter(state=state)


class FlowVersionManager(models.Manager.from_queryset(FlowVersionQuerySet)):
    pass


class FlowVersion(BaseModel):
    """Immutable snapshot of a flow's configuration."""

    class FlowVersionState(models.TextChoices):
        DRAFT = "draft", _("Draft")
        PUBLISHED = "published", _("Published")
        DISABLED = "disabled", _("Disabled")

    flow = models.ForeignKey(
        Flow,
        on_delete=models.CASCADE,
        related_name="versions",
        verbose_name=_("Flow"),
    )
    version_number = models.PositiveIntegerField(_("Version number"))
    name = models.CharField(_("Name"), max_length=250)
    description = models.CharField(_("Description"), max_length=1000, blank=True, default="")
    flow_configurations = models.JSONField(_("Flow configurations"), default=dict, blank=True)
    flow_json = models.JSONField(_("Flow JSON"))
    state = models.CharField(
        _("State"),
        max_length=20,
        choices=FlowVersionState.choices,
        default=FlowVersionState.DRAFT,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="flow_versions",
        verbose_name=_("Created by"),
    )

    objects = FlowVersionManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ["-version_number", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["flow", "version_number"],
                name="uq_flow_version_sequence",
            ),
            models.UniqueConstraint(
                fields=["flow", "state"],
                condition=Q(is_active=True),
                name="uq_flow_state_active_version",
            ),
        ]
        indexes = [
            models.Index(fields=["flow", "version_number"], name="ix_flow_version"),
        ]

    def clean(self):
        super().clean()
        if self.name:
            self.name = self.name.strip()
        if not self.name:
            raise ValidationError({"name": _("Name is required.")})
        if len(self.name) > 250:
            raise ValidationError({"name": _("Name must be 250 characters or fewer.")})
        if self.description is not None:
            self.description = (self.description or "").strip()
            if len(self.description) > 1000:
                raise ValidationError({"description": _("Description must be 1000 characters or fewer.")})
        self.flow_configurations = validate_flow_configurations(self.flow_configurations or {})
        self.flow_json = validate_flow_json(self.flow_json or {})

    def deactivate(self):
        if not self.is_active:
            return
        self.is_active = False
        self.save(update_fields=["is_active", "updated_at"])

    def activate(self):
        if self.is_active:
            return
        self.is_active = True
        self.save(update_fields=["is_active", "updated_at"])

    def __str__(self):
        return f"Flow {self.flow_id} v{self.version_number} ({self.state})"
