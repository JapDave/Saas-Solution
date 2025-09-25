# apps/common/db/softdelete.py
from __future__ import annotations
import uuid
from django.db import models
from django.utils import timezone


class SoftDeleteQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def deleted(self):
        return self.filter(deleted_at__isnull=False)

    # bulk helpers (no hard delete support)
    def soft_delete(self):
        return super().update(deleted_at=timezone.now())

    def restore(self):
        return super().update(deleted_at=None)


class SoftDeleteManager(models.Manager):
    """Default manager: only non-deleted rows."""
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).alive()

    # convenience accessors
    def deleted(self):
        return SoftDeleteQuerySet(self.model, using=self._db).deleted()

    def all_with_deleted(self):
        return SoftDeleteQuerySet(self.model, using=self._db).all()


class BaseModel(models.Model):
    """Abstract: UUID pk + timestamps + is_active + soft-delete fields."""
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    # managers
    objects = SoftDeleteManager()
    all_objects = SoftDeleteManager()  # includes alive by default; use .all_with_deleted() when needed

    class Meta:
        abstract = True

    # soft delete only (no hard delete in project)
    def delete(self, using=None, keep_parents=False):
        self.soft_delete()

    def soft_delete(self):
        if self.deleted_at:
            return  # idempotent
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at", "updated_at"])

    def restore(self):
        self.deleted_at = None
        self.save(update_fields=["deleted_at", "updated_at"])
