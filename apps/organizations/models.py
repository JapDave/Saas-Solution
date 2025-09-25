# apps/organizations/models.py
from __future__ import annotations
from django.db import models
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db.models.functions import Lower
from django.db.models import Q

from apps.common.db.softdelete import BaseModel


class OrganizationQuerySet(models.QuerySet):
    def search(self, q: str | None):
        if not q:
            return self
        return self.filter(
            Q(name__icontains=q) |
            Q(description__icontains=q)
        )

    def for_account(self, account_id):
        return self.filter(account_id=account_id)


class Organization(BaseModel):
    """
    Inherits from BaseModel:
      - id (UUID pk), is_active (bool), created_at, updated_at, deleted_at
      - default manager hides soft-deleted rows
    """
    account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.CASCADE,
        related_name="organizations",
    )
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

    # attach custom queryset on top of BaseModel manager
    objects = models.Manager.from_queryset(OrganizationQuerySet)()

    class Meta:
        db_table = "organizations_organization"
        indexes = [
            models.Index(Lower("name"), name="ix_org_name_ci"),
            models.Index(models.F("account"), name="ix_org_account"),
        ]
        constraints = [
            # Unique org name within an account, case-insensitive (PostgreSQL recommended)
            models.UniqueConstraint(
                Lower("name"),
                "account",
                name="uq_org_account_name_ci",
            ),
            # Prevent duplicate (account, name) among non-deleted rows if your DB supports partial constraint
            # models.UniqueConstraint(
            #     fields=["account", "name"],
            #     condition=Q(deleted_at__isnull=True),
            #     name="uq_org_account_name_alive",
            # ),
        ]

    def clean(self):
        super().clean()
        if not (1 <= len(self.name) <= 100):
            raise ValidationError({"name": "Name must be 1-100 characters."})
        if self.description and len(self.description) > 500:
            raise ValidationError({"description": "Description must be ≤ 500 characters."})

    def __str__(self):
        return f"{self.name} @ {self.account_id}"
