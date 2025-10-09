from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import Account
from apps.common.models import BaseModel


class OrganizationQuerySet(models.QuerySet):
    """Custom queryset with helpers for soft-deleted filtering and search."""

    def alive(self):
        """Return only organizations that have not been soft deleted."""

        return self.filter(deleted_at__isnull=True)

    def search(self, q: str | None, account_id: int | None = None):
        """Filter organizations by account scope and substring search."""

        queryset = self
        if account_id is not None:
            queryset = queryset.filter(account_id=account_id)
        if not q:
            return queryset
        return queryset.filter(
            models.Q(name__icontains=q) |
            models.Q(description__icontains=q)
        )


class OrganizationManager(models.Manager.from_queryset(OrganizationQuerySet)):
    """Default manager that hides soft-deleted organizations from queries."""

    def get_queryset(self):
        return super().get_queryset().alive()


class Organization(BaseModel):
    """Tenant-level organization record that belongs to an account."""

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="organizations", verbose_name=_("Account"))
    name = models.CharField(_("Name"), max_length=100)
    description = models.CharField(_("Description"), max_length=500, blank=True, default="")
    logo_url = models.URLField(_("Logo URL"), blank=True, default="")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="organizations_created",
        verbose_name=_("Created by"),
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="organizations_updated",
        verbose_name=_("Updated by"),
    )

    objects = OrganizationManager()
    _all_objects = models.Manager()

    class Meta:
        indexes = [
            models.Index(fields=["name"], name="ix_org_name"),
            models.Index(fields=["account"], name="ix_org_account"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["name", "account"], name="uq_org_name_per_account"),
        ]

    def __str__(self) -> str:
        return f"{self.name} (acct={self.account_id})"

