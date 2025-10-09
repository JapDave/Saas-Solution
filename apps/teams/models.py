from __future__ import annotations

from typing import Optional

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel


class TeamQuerySet(models.QuerySet):
    """Custom queryset helpers for teams."""

    def alive(self) -> models.QuerySet:
        """Only teams that are not soft-deleted."""

        return self.filter(deleted_at__isnull=True)

    def search(self, term: Optional[str] = None, *, organization_id: Optional[int] = None) -> models.QuerySet:
        """Filter by organization and case-insensitive substring on name/description."""

        queryset = self
        if organization_id is not None:
            queryset = queryset.filter(organization_id=organization_id)
        if term:
            queryset = queryset.filter(
                Q(name__icontains=term) | Q(description__icontains=term)
            )
        return queryset


class TeamManager(models.Manager.from_queryset(TeamQuerySet)):
    """Default manager that hides soft-deleted teams."""

    def get_queryset(self) -> models.QuerySet:
        return super().get_queryset().alive()


class Team(BaseModel):
    """Team within an organization."""

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="teams",
        verbose_name=_("Organization"),
    )
    name = models.CharField(_("Name"), max_length=100)
    description = models.CharField(_("Description"), max_length=500, blank=True, default="")
    configurations = models.JSONField(_("Configurations"), default=dict, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="teams_created",
        verbose_name=_("Created by"),
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="teams_updated",
        verbose_name=_("Updated by"),
    )

    objects = TeamManager()
    _all_objects = models.Manager()

    class Meta:
        indexes = [
            models.Index(fields=["name"], name="ix_team_name"),
            models.Index(fields=["organization"], name="ix_team_organization"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "organization"],
                condition=Q(deleted_at__isnull=True),
                name="uq_team_name_per_org",
            )
        ]

    def clean(self):
        super().clean()
        if self.configurations is None:
            self.configurations = {}
        if not isinstance(self.configurations, dict):
            raise ValidationError({"configurations": _("Configurations must be a JSON object.")})
        if self.deleted_at and self.is_active:
            raise ValidationError({"is_active": _("Deleted teams cannot be active.")})
        if not self.name or not self.name.strip():
            raise ValidationError({"name": _("Name is required.")})
        if len(self.name.strip()) > 100:
            raise ValidationError({"name": _("Name must be 100 characters or fewer.")})
        if self.description and len(self.description) > 500:
            raise ValidationError({"description": _("Description must be 500 characters or fewer.")})

    def __str__(self) -> str:
        return f"{self.name} (org={self.organization_id})"


class TeamMemberQuerySet(models.QuerySet):
    """Helpers for membership queries."""

    def alive(self) -> models.QuerySet:
        return self.filter(deleted_at__isnull=True)

    def active(self) -> models.QuerySet:
        return self.alive().filter(is_active=True)


class TeamMemberManager(models.Manager.from_queryset(TeamMemberQuerySet)):
    def get_queryset(self) -> models.QuerySet:
        return super().get_queryset().alive()


class TeamMember(BaseModel):
    """Membership of a user within a team."""

    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.CASCADE,
        related_name="memberships",
        verbose_name=_("Team"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="team_memberships",
        verbose_name=_("User"),
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="team_memberships_assigned",
        verbose_name=_("Assigned by"),
    )
    assigned_at = models.DateTimeField(_("Assigned at"), auto_now_add=True, db_index=True)
    role_keys = models.JSONField(_("Role keys"), default=list, blank=True)

    objects = TeamMemberManager()
    all_objects = models.Manager()

    class Meta:
        indexes = [
            models.Index(fields=["team", "user"], name="ix_team_member_lookup"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "user"],
                condition=Q(deleted_at__isnull=True),
                name="uq_active_team_member",
            )
        ]

    def clean(self):
        super().clean()
        if self.role_keys is None:
            self.role_keys = []
        if not isinstance(self.role_keys, list):
            raise ValidationError({"role_keys": _("role_keys must be a list of permission keys.")})
        invalid = [key for key in self.role_keys if not isinstance(key, str) or not key.strip()]
        if invalid:
            raise ValidationError({"role_keys": _("Each role key must be a non-empty string.")})
        if getattr(self.team, "organization_id", None) is None:
            raise ValidationError({"team": _("Team must be associated with an organization.")})
        organization_id = self.team.organization_id
        from apps.users.models import UserOrganization  # local import to avoid circular

        membership_exists = UserOrganization.objects.filter(
            user=self.user,
            organization_id=organization_id,
            deleted_at__isnull=True,
            is_active=True,
        ).exists()
        if not membership_exists:
            raise ValidationError({"user": _("User must be an active member of the organization.")})
        if self.deleted_at and self.is_active:
            raise ValidationError({"is_active": _("Deleted memberships cannot be active.")})

    def deactivate(self):
        if self.deleted_at:
            return
        if self.is_active:
            self.is_active = False
            self.save(update_fields=["is_active", "updated_at"])

    def __str__(self) -> str:
        return f"team={self.team_id} user={self.user_id}"
