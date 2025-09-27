from __future__ import annotations
from django.db import models
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db.models.functions import Lower

from apps.common.models import BaseModel
from apps.accounts.models import Account


class OrganizationQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def search(self, q: str | None, account_id: int | None = None):
        qs = self
        if account_id is not None:
            qs = qs.filter(account_id=account_id)
        if not q:
            return qs
        return qs.filter(
            models.Q(name__icontains=q) |
            models.Q(description__icontains=q)
        )


class OrganizationManager(models.Manager.from_queryset(OrganizationQuerySet)):
    def get_queryset(self):
        # hide soft-deleted rows by default
        return super().get_queryset().alive()


class Organization(BaseModel):
    """
    Inherits BaseModel fields:
      id (pk), is_active, created_at, updated_at, deleted_at
    """
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="organizations")
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=500, blank=True, default="")
    logo_url = models.URLField(blank=True, default="")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="organizations_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="organizations_updated",
    )

    objects = OrganizationManager()          # hides soft-deleted
    _all_objects = models.Manager()          # raw access if ever needed

    class Meta:
        indexes = [
            models.Index(Lower("name"), name="ix_org_name_ci"),
            models.Index(models.F("account"), name="ix_org_account"),
        ]
        constraints = [
            # name unique *within account*, case-insensitive
            models.UniqueConstraint(Lower("name"), "account", name="uq_org_name_per_account_ci"),
        ]

    def __str__(self):
        return f"{self.name} (acct={self.account_id})"
