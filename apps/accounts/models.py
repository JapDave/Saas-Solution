# apps/accounts/models.py
from __future__ import annotations
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel

class AccountQuerySet(models.QuerySet):
    """Custom queryset with helpers that ignore soft-deleted accounts."""
    def alive(self):
        """Return only accounts that have not been soft deleted."""
        return self.filter(deleted_at__isnull=True)

    def search(self, q: str | None):
        """Filter accounts by a case-insensitive match on name or contact email."""
        if not q:
            return self
        return self.filter(
            models.Q(name__icontains=q) |
            models.Q(contact_email__icontains=q)
        )

class AccountManager(models.Manager.from_queryset(AccountQuerySet)):
    """Default manager that hides soft-deleted accounts from queries."""
    def get_queryset(self):
        # hide soft-deleted rows by default
        return super().get_queryset().alive()

class Account(BaseModel):
    """
    Inherits BaseModel fields:
      id (pk), is_active, created_at, updated_at, deleted_at
    """
    name = models.CharField(_("Name"), max_length=100)
    description = models.CharField(_("Description"), max_length=500, blank=True, default="")
    contact_email = models.EmailField(_("Contact email"), unique=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="accounts_created",
        verbose_name=_("Created by"),
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="accounts_updated",
        verbose_name=_("Updated by"),
    )

    objects = AccountManager()               # hides soft-deleted
    _all_objects = models.Manager()          # raw access if ever needed

    class Meta:
        indexes = [models.Index(fields=["name"], name="ix_account_name")]
        constraints = [models.UniqueConstraint(fields=["name"], name="uq_account_name")]

    def __str__(self):
        return self.name

