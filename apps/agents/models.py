from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel
from apps.agents.validators import (
    validate_llm_configuration,
    validate_system_prompts,
    validate_tools_configuration,
)


class AgentQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def for_organization(self, organization):
        org_id = getattr(organization, "id", organization)
        return self.filter(organization_id=org_id)


class AgentManager(models.Manager.from_queryset(AgentQuerySet)):
    def get_queryset(self):
        return super().get_queryset().alive()


class Agent(BaseModel):
    """Represents an agent definition scoped to an organization."""

    class AgentState(models.TextChoices):
        DRAFT = "draft", _("Draft")
        ACTIVE = "active", _("Active")
        ARCHIVED = "archived", _("Archived")
        DELETED = "deleted", _("Deleted")

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="agents",
        verbose_name=_("Organization"),
    )
    name = models.CharField(_("Name"), max_length=250)
    description = models.CharField(_("Description"), max_length=250, blank=True, default="")
    system_prompts = models.TextField(_("System Prompts"), blank=True, default="")
    llm_configuration = models.JSONField(_("LLM configuration"), default=dict, blank=True)
    tools_configuration = models.JSONField(_("Tools configuration"), default=list, blank=True)
    current_version = models.ForeignKey(
        "agents.AgentVersion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="active_agents",
        verbose_name=_("Current version"),
    )
    state = models.CharField(
        _("State"),
        max_length=20,
        choices=AgentState.choices,
        default=AgentState.DRAFT,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="agents_created",
        verbose_name=_("Created by"),
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="agents_updated",
        verbose_name=_("Updated by"),
    )

    objects = AgentManager()
    all_objects = models.Manager()

    class Meta:
        indexes = [
            models.Index(fields=["organization", "name"], name="ix_agent_org_name"),
            models.Index(fields=["state"], name="ix_agent_state"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                condition=Q(deleted_at__isnull=True),
                name="uq_agent_name_per_org",
            )
        ]

    def clean(self):
        super().clean()
        if self.system_prompts:
            validate_system_prompts(self.system_prompts)
        if self.llm_configuration:
            validate_llm_configuration(self.llm_configuration, organization=self.organization)
        if self.tools_configuration:
            validate_tools_configuration(self.tools_configuration, organization=self.organization)
        if len((self.description or "")) > 250:
            raise ValidationError({"description": _("Description must be 250 characters or fewer.")})
        if self.name and len(self.name.strip()) > 250:
            self.name = self.name.strip()
        if not self.name:
            raise ValidationError({"name": _("Name is required.")})

    def mark_deleted(self):
        """Transition to deleted state while retaining versions."""

        self.state = self.AgentState.DELETED
        self.deleted_at = timezone.now()
        self.save(update_fields=["state", "deleted_at", "updated_at"])

    def __str__(self):
        return f"{self.name} ({self.organization_id})"


class AgentVersion(BaseModel):
    """Immutable snapshot of agent configuration."""

    agent = models.ForeignKey(
        Agent,
        on_delete=models.CASCADE,
        related_name="versions",
        verbose_name=_("Agent"),
    )
    version_number = models.PositiveIntegerField(_("Version number"))
    name = models.CharField(_("Name"), max_length=250)
    description = models.CharField(_("Description"), max_length=250, blank=True, default="")
    system_prompts = models.TextField(_("System Prompts"))
    llm_configuration = models.JSONField(_("LLM configuration"))
    tools_configuration = models.JSONField(_("Tools configuration"), default=list, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="agent_versions_created",
        verbose_name=_("Created by"),
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["agent", "version_number"],
                name="uq_agent_version_seq",
            )
        ]

    def clean(self):
        super().clean()
        validate_system_prompts(self.system_prompts)
        validate_llm_configuration(self.llm_configuration, organization=self.agent.organization)
        validate_tools_configuration(self.tools_configuration, organization=self.agent.organization)

    def __str__(self):
        return f"Agent {self.agent_id} v{self.version_number}"


class OrganizationEnabledLLM(BaseModel):
    """Records which LLMs are enabled for an organization."""

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="enabled_llms",
        verbose_name=_("Organization"),
    )
    model_key = models.CharField(_("Model key"), max_length=100)
    model_provider = models.CharField(_("Model provider"), max_length=100)
    enabled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="enabled_llms",
        verbose_name=_("Enabled by"),
    )
    enabled_at = models.DateTimeField(_("Enabled at"), auto_now_add=True)
    disabled_at = models.DateTimeField(_("Disabled at"), null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "model_key"],
                condition=Q(disabled_at__isnull=True),
                name="uq_enabled_llm_per_org",
            )
        ]

    def disable(self, *, actor=None):
        if self.disabled_at:
            return
        self.disabled_at = timezone.now()
        self.save(update_fields=["disabled_at", "updated_at"])

    def __str__(self):
        state = "enabled" if not self.disabled_at else "disabled"
        return f"{self.model_key} ({state})"


class OrganizationEnabledTool(BaseModel):
    """Records which tools are enabled for an organization."""

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="enabled_tools",
        verbose_name=_("Organization"),
    )
    tool_key = models.CharField(_("Tool key"), max_length=100)
    enabled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="enabled_tools",
        verbose_name=_("Enabled by"),
    )
    enabled_at = models.DateTimeField(_("Enabled at"), auto_now_add=True)
    disabled_at = models.DateTimeField(_("Disabled at"), null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "tool_key"],
                condition=Q(disabled_at__isnull=True),
                name="uq_enabled_tool_per_org",
            )
        ]

    def disable(self, *, actor=None):
        if self.disabled_at:
            return
        self.disabled_at = timezone.now()
        self.save(update_fields=["disabled_at", "updated_at"])

    def __str__(self):
        state = "enabled" if not self.disabled_at else "disabled"
        return f"{self.tool_key} ({state})"
