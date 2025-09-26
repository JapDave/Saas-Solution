# apps/common/models.py
from __future__ import annotations
import uuid
from django.db import models
from django.utils import timezone
from django.conf import settings

class BaseQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(deleted_at__isnull=True)
    def deleted(self):
        return self.filter(deleted_at__isnull=False)

class BaseManager(models.Manager.from_queryset(BaseQuerySet)):  # hides deleted by default
    def get_queryset(self):
        return super().get_queryset().alive()

class BaseModel(models.Model):
    """
    Minimal reusable base (NO ForeignKeys here):
      - id (UUID pk)
      - is_active (bool)
      - created_at / updated_at
      - deleted_at (soft delete)
      - default manager hides soft-deleted rows
    """
    uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = BaseManager()         # hides soft-deleted rows
    all_objects = models.Manager()  # includes deleted if you really need them

    class Meta:
        abstract = True

    # Soft delete only
    def delete(self, using=None, keep_parents=False):
        if self.deleted_at:
            return
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at", "updated_at"])

    def restore(self):
        if self.deleted_at is None:
            return
        self.deleted_at = None
        self.save(update_fields=["deleted_at", "updated_at"])

class AuditLog(models.Model):
    """Simple audit log record."""
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    method = models.CharField(max_length=8)
    path = models.CharField(max_length=512, db_index=True)
    view = models.CharField(max_length=256, blank=True, default="")
    app_label = models.CharField(max_length=64, blank=True, default="")
    model = models.CharField(max_length=64, blank=True, default="")
    action = models.CharField(max_length=32, blank=True, default="")
    object_id = models.CharField(max_length=64, blank=True, default="")
    status_code = models.IntegerField()
    success = models.BooleanField(default=False)
    ip_addr = models.GenericIPAddressField(null=True, blank=True)
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["path"]),
            models.Index(fields=["app_label", "model", "action"]),
        ]
