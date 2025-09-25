# apps/accounts/models.py
from __future__ import annotations
from django.db import models
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db.models.functions import Lower

from apps.common.models import BaseModel


class AccountQuerySet(models.QuerySet):
    def search(self, q: str | None):
        if not q:
            return self
        return self.filter(
            models.Q(name__icontains=q) |
            models.Q(contact_email__icontains=q)
        )


class Account(BaseModel):
    """
    Fields inherited from BaseModel:
      - id (UUID pk), is_active, created_at, updated_at, deleted_at
      - objects manager hides soft-deleted rows
    """
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=500, blank=True, default="")
    contact_email = models.EmailField(unique=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="accounts_created"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="accounts_updated"
    )

    # custom queryset layered on default manager
    objects = models.Manager.from_queryset(AccountQuerySet)()

    class Meta:
        db_table = "accounts_account"
        indexes = [
            models.Index(Lower("name"), name="ix_account_name_ci"),
        ]
        constraints = [
            models.UniqueConstraint(Lower("name"), name="uq_account_name_ci"),
        ]

    def clean(self):
        super().clean()
        if not (1 <= len(self.name) <= 100):
            raise ValidationError({"name": "Name must be 1-100 characters."})
        if self.description and len(self.description) > 500:
            raise ValidationError({"description": "Description must be ≤ 500 characters."})

    def __str__(self):
        return self.name
