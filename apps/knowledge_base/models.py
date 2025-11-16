from __future__ import annotations

import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel
from apps.files.models import File

ALLOWED_EXTENSIONS = {"pdf", "docx", "doc", "txt", "md"}
MAX_RESOURCE_SIZE = 50 * 1024 * 1024  # 50MB


class CollectionQuerySet(models.QuerySet):
    def alive(self):
        return self.exclude(state=Collection.CollectionState.DELETED)

    def for_organization(self, organization):
        org_id = getattr(organization, "id", organization)
        return self.filter(organization_id=org_id)


class CollectionManager(models.Manager.from_queryset(CollectionQuerySet)):
    def get_queryset(self):
        return super().get_queryset().alive()


class Collection(BaseModel):
    class CollectionState(models.TextChoices):
        DRAFT = "draft", _("Draft")
        ACTIVE = "active", _("Active")
        ARCHIVED = "archived", _("Archived")
        DELETED = "deleted", _("Deleted")

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="knowledge_collections",
        verbose_name=_("Organization"),
    )
    name = models.CharField(_("Name"), max_length=255)
    description = models.CharField(_("Description"), max_length=1000, blank=True, default="")
    version = models.PositiveIntegerField(_("Version"), default=1)
    state = models.CharField(
        _("State"),
        max_length=20,
        choices=CollectionState.choices,
        default=CollectionState.DRAFT,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="knowledge_collections_created",
        verbose_name=_("Created by"),
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="knowledge_collections_updated",
        verbose_name=_("Updated by"),
    )

    objects = CollectionManager()
    all_objects = models.Manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                condition=Q(state__in=["draft", "active", "archived"]),
                name="uq_collection_name_per_org",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "name"], name="ix_collection_org_name"),
        ]

    def clean(self):
        super().clean()
        if self.name:
            self.name = self.name.strip()
        if not self.name:
            raise ValidationError({"name": _("Name is required.")})
        if len(self.name) > 255:
            raise ValidationError({"name": _("Name must be 255 characters or fewer.")})
        if self.description and len(self.description) > 1000:
            raise ValidationError({"description": _("Description must be 1000 characters or fewer.")})

    def bump_version(self, *, actor=None):
        self.version += 1
        self.updated_by = actor or self.updated_by
        self.save(update_fields=["version", "updated_by", "updated_at"])

    def mark_deleted(self):
        if self.state == self.CollectionState.DELETED:
            return
        self.state = self.CollectionState.DELETED
        self.deleted_at = timezone.now()
        self.save(update_fields=["state", "deleted_at", "updated_at"])

    def delete(self, using=None, keep_parents=False):
        self.mark_deleted()

    def __str__(self):
        return f"{self.name} ({self.organization_id})"


class Resource(BaseModel):
    class ResourceType(models.TextChoices):
        FAQ = "faq", _("FAQ")
        LEGAL = "legal", _("Legal Document")
        GENERAL = "general", _("General Document")

    collection = models.ForeignKey(
        Collection,
        on_delete=models.CASCADE,
        related_name="resources",
        verbose_name=_("Collection"),
    )
    file = models.ForeignKey(
        "files.File",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="collection_resources",
        verbose_name=_("File"),
    )
    file_uuid = models.UUIDField(_("File UUID"))
    file_type = models.CharField(_("File type"), max_length=20)
    resource_type = models.CharField(
        _("Resource type"),
        max_length=20,
        choices=ResourceType.choices,
        default=ResourceType.GENERAL,
    )
    title = models.CharField(_("Title"), max_length=255, blank=True, default="")
    summary = models.CharField(_("Summary"), max_length=1000, blank=True, default="")
    is_broken_reference = models.BooleanField(_("Broken reference"), default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="knowledge_resources_created",
        verbose_name=_("Created by"),
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="knowledge_resources_updated",
        verbose_name=_("Updated by"),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["collection", "file_uuid"],
                condition=Q(deleted_at__isnull=True),
                name="uq_resource_file_per_collection",
            )
        ]
        indexes = [
            models.Index(fields=["collection", "resource_type"], name="ix_resource_collection_type"),
        ]

    def clean(self):
        super().clean()
        if self.title and len(self.title) > 255:
            raise ValidationError({"title": _("Title must be 255 characters or fewer.")})
        if self.summary and len(self.summary) > 1000:
            raise ValidationError({"summary": _("Summary must be 1000 characters or fewer.")})
        if self.file_type and self.file_type.lower() not in ALLOWED_EXTENSIONS:
            raise ValidationError({"file_type": _("File type not allowed.")})

    def refresh_file_reference(self):
        try:
            file = File.objects.get(uuid=self.file_uuid, organization=self.collection.organization)
        except File.DoesNotExist:
            self.file = None
            self.is_broken_reference = True
            return
        self.file = file
        extension = Path(file.name).suffix.lstrip(".").lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise ValidationError({"file_uuid": _("File type not allowed for knowledge resources.")})
        if file.size > MAX_RESOURCE_SIZE:
            raise ValidationError({"file_uuid": _("File exceeds the 50MB limit.")})
        self.file_type = extension
        self.is_broken_reference = False

    def save(self, *args, **kwargs):
        if not self.file_uuid:
            raise ValidationError({"file_uuid": _("fileId is required.")})
        if isinstance(self.file_uuid, str):
            try:
                self.file_uuid = uuid.UUID(self.file_uuid)
            except ValueError as exc:
                raise ValidationError({"file_uuid": _("fileId must be a valid UUID.")}) from exc
        if not kwargs.pop("skip_file_refresh", False):
            self.refresh_file_reference()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.collection_id}:{self.file_uuid}"
