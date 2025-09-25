# apps/users/models.py
from __future__ import annotations
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from apps.common.models import BaseModel
from django.db.models import Q

class User(AbstractUser, BaseModel):
    full_name = models.CharField(max_length=200, blank=True)
    email = models.EmailField()
    organization = models.ForeignKey(
        "organizations.Organization", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="users"
    )
    # Remove if you decided to go pure RBAC; otherwise keep internal-only
    is_org_admin = models.BooleanField(default=False)

    profile_image = models.URLField(blank=True)
    user_preferences = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="created_users")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization","email"], name="uniq_email_per_org")]

    def __str__(self):
        return self.username or self.email

# --- Membership: user belongs to organization(s) ----------------------------

class UserOrganization(BaseModel):
    """
    Membership record of a user in an organization.
    Soft-deletable; unique (user, organization) while alive.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="members",
    )
    class Meta:
        db_table = "users_user_organization"
        indexes = [
            models.Index("user", name="ix_uo_user"),
            models.Index("organization", name="ix_uo_org"),
        ]
        constraints = [
            # Ensure a user can only have one alive membership per organization
            models.UniqueConstraint(
                fields=["user", "organization"],
                condition=Q(deleted_at__isnull=True),
                name="uq_uo_user_org_alive",
            ),
        ]

    def __str__(self):
        return f"{self.user} → {self.organization}"
