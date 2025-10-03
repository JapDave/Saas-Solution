from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel


class Role(BaseModel):
    """
    Represents a role within an organization, defining a set of permissions.
    """

    class RoleType(models.TextChoices):
        SYSTEM = "system", _("System")
        USER = "user", _("User")  # Maintained by Hudhud, but customizable
        PREDEFINED_CUSTOM = "predefined_custom", _("Predefined Custom")
        USER_CUSTOM = "user_custom", _("User Custom")

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="roles",
        null=True,  # System roles are not tied to an organization
        blank=True,
    )
    name = models.CharField(max_length=100)
    description = models.TextField(max_length=500, blank=True)
    permissions = ArrayField(
        models.CharField(max_length=100),
        default=list,
        blank=True,
        help_text=_("List of permission keys associated with this role."),
    )
    role_type = models.CharField(
        max_length=20,
        choices=RoleType.choices,
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_roles",
        null=True,
        blank=False,
    )

    class Meta:
        verbose_name = _("Role")
        verbose_name_plural = _("Roles")
        # A role name must be unique within an organization.
        # System roles (organization is NULL) must have unique names among themselves.
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"], name="unique_organization_role_name"
            )
        ]
        ordering = ["organization", "name"]

    def __str__(self):
        if self.organization:
            return f"{self.name} ({self.organization.name})"
        return f"{self.name} (System)"


class RoleAssignment(BaseModel):
    """
    Assigns a Role to a User within a specific Organization.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="role_assignments"
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="role_assignments",
    )
    role = models.ForeignKey(
        Role, on_delete=models.CASCADE, related_name="assignments"
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="made_role_assignments",
        null=True,
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Role Assignment")
        verbose_name_plural = _("Role Assignments")
        # A user can only be assigned a specific role once within an organization
        constraints = [
            models.UniqueConstraint(
                fields=["user", "organization", "role"], name="unique_user_org_role"
            )
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} as {self.role} in {self.organization}"
