from __future__ import annotations

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.channels.definitions import CHANNEL_TYPE_CHOICES
from apps.channels.validators import validate_channel_configuration
from apps.common.models import BaseModel


class ChannelQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(deleted_at__isnull=True)


class ChannelManager(models.Manager.from_queryset(ChannelQuerySet)):
    def get_queryset(self):
        return super().get_queryset().alive()


class Channel(BaseModel):
    class ChannelState(models.TextChoices):
        INACTIVE = "inactive", _("Inactive")
        ACTIVE = "active", _("Active")
        DELETED = "deleted", _("Deleted")

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="channels",
        verbose_name=_("Organization"),
    )
    channel_type = models.CharField(
        _("Channel Type"),
        max_length=20,
        choices=CHANNEL_TYPE_CHOICES,
    )
    name = models.CharField(_("Name"), max_length=500)
    description = models.CharField(_("Description"), max_length=500, blank=True, default="")
    state = models.CharField(
        _("State"),
        max_length=20,
        choices=ChannelState.choices,
        default=ChannelState.INACTIVE,
    )
    configurations = models.JSONField(_("Configurations"), default=dict)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="channels_created",
        verbose_name=_("Created by"),
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="channels_updated",
        verbose_name=_("Updated by"),
    )

    objects = ChannelManager()
    all_objects = models.Manager()

    class Meta:
        indexes = [
            models.Index(fields=["organization", "channel_type"], name="ix_channel_org_type"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                condition=Q(deleted_at__isnull=True),
                name="uq_channel_name_per_org",
            )
        ]

    def clean(self):
        super().clean()
        if not self.name or len(self.name.strip()) == 0:
            raise ValidationError({"name": _("Name is required.")})
        if len(self.name.strip()) > 500:
            raise ValidationError({"name": _("Name must be 500 characters or fewer.")})
        self.name = self.name.strip()
        if self.description:
            self.description = self.description.strip()
        self.configurations = validate_channel_configuration(
            self.channel_type,
            self.configurations or {},
        )

    def mark_deleted(self):
        if self.state == self.ChannelState.DELETED:
            return
        self.state = self.ChannelState.DELETED
        self.deleted_at = timezone.now()
        self.save(update_fields=["state", "deleted_at", "updated_at"])

    def delete(self, using=None, keep_parents=False):
        self.mark_deleted()

    def __str__(self):
        return f"{self.name} ({self.channel_type})"


class ChannelAccessGrant(BaseModel):
    class SubjectType(models.TextChoices):
        USER = "user", _("User")
        TEAM = "team", _("Team")

    channel = models.ForeignKey(
        Channel,
        on_delete=models.CASCADE,
        related_name="grants",
        verbose_name=_("Channel"),
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="channel_grants",
        verbose_name=_("Organization"),
    )
    subject_type = models.CharField(
        _("Subject type"),
        max_length=10,
        choices=SubjectType.choices,
    )
    subject_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="channel_grants",
    )
    subject_team = models.ForeignKey(
        "teams.Team",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="channel_grants",
    )
    permissions = ArrayField(
        models.CharField(max_length=50),
        default=list,
        blank=True,
        verbose_name=_("Permissions"),
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="channel_grants_made",
        verbose_name=_("Granted by"),
    )
    granted_at = models.DateTimeField(_("Granted at"), auto_now_add=True)
    revoked_at = models.DateTimeField(_("Revoked at"), null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["channel", "subject_type"], name="ix_channel_grant_subject"),
        ]

    def clean(self):
        super().clean()
        if self.subject_type == self.SubjectType.USER:
            if not self.subject_user_id:
                raise ValidationError({"subject_user": _("User must be provided for user grants.")})
            self.subject_team = None
        elif self.subject_type == self.SubjectType.TEAM:
            if not self.subject_team_id:
                raise ValidationError({"subject_team": _("Team must be provided for team grants.")})
            self.subject_user = None
        else:
            raise ValidationError({"subject_type": _("Invalid grant subject type.")})
        if not self.permissions:
            raise ValidationError({"permissions": _("At least one permission is required.")})
        normalized = sorted({perm.strip() for perm in self.permissions if perm})
        if not normalized:
            raise ValidationError({"permissions": _("Permissions cannot be blank.")})
        self.permissions = normalized

    def revoke(self, *, actor=None):
        if self.revoked_at:
            return
        self.revoked_at = timezone.now()
        self.save(update_fields=["revoked_at", "updated_at"])

    def __str__(self):
        target = self.subject_user or self.subject_team
        return f"{self.channel_id} -> {target}"
