import uuid
from django.db import models
from django.db.models.functions import Lower
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.conf import settings


class AccountQuerySet(models.QuerySet):
    def not_deleted(self):
        return self.exclude(deleted_at__isnull=True)

    def search(self, q: str):
        if not q:
            return self
        return self.filter(
            models.Q(name__icontains=q) | models.Q(contact_email__icontains=q)
        )


class Account(models.Model):

    account_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=500, blank=True, default="")
    contact_email = models.EmailField(unique=True)

    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,  
        related_name="created_accounts",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = AccountQuerySet.as_manager()

    class Meta:
        db_table = "accounts_account"
        indexes = [
            models.Index(Lower("name"), name="ix_account_name_ci"),
        ]
        constraints = [
            # Case-insensitive uniqueness for name
            models.UniqueConstraint(
                Lower("name"),
                name="uq_account_name_ci",
            )
        ]

    def clean(self):
        super().clean()
        if not (1 <= len(self.name) <= 100):
            raise ValidationError({"name": "Name must be 1-100 characters."})
        if self.description and len(self.description) > 500:
            raise ValidationError({"description": "Description must be ≤ 500 characters."})

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at", "updated_at"])

    def __str__(self):
        return f"{self.name}"
