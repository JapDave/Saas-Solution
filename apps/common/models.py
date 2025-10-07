# apps/common/models.py
from __future__ import annotations
import uuid
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
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
    uuid = models.UUIDField(_("UUID"), unique=True, default=uuid.uuid4, editable=False)
    is_active = models.BooleanField(_("Is active"), default=True, db_index=True)
    created_at = models.DateTimeField(_("Created at"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("Updated at"), auto_now=True)
    deleted_at = models.DateTimeField(_("Deleted at"), null=True, blank=True, db_index=True)

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
    created_at = models.DateTimeField(_("Created at"), default=timezone.now, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_("User"))
    method = models.CharField(_("HTTP method"), max_length=8)
    path = models.CharField(_("Path"), max_length=512, db_index=True)
    view = models.CharField(_("View name"), max_length=256, blank=True, default="")
    app_label = models.CharField(_("App label"), max_length=64, blank=True, default="")
    model = models.CharField(_("Model name"), max_length=64, blank=True, default="")
    action = models.CharField(_("Action"), max_length=32, blank=True, default="")
    object_id = models.CharField(_("Object ID"), max_length=64, blank=True, default="")
    status_code = models.IntegerField(_("Status code"))
    success = models.BooleanField(_("Was successful"), default=False)
    ip_addr = models.GenericIPAddressField(_("IP address"), null=True, blank=True)
    extra = models.JSONField(_("Extra metadata"), default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["path"]),
            models.Index(fields=["app_label", "model", "action"]),
        ]
