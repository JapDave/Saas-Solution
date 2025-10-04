import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel


def validate_no_path_separators(value):
    """Validator to ensure the filename does not contain path separators."""
    if '/' in value or '\\' in value:
        raise ValidationError(
            _("Filename cannot contain path separators ('/' or '\\')."),
            code='invalid_filename'
        )


def validate_tags(value):
    """Validator for the tags array field."""
    if not isinstance(value, list):
        raise ValidationError(_("Tags must be a list of strings."))
    if len(value) > 10:
        raise ValidationError(_("A maximum of 10 tags are allowed."))
    for tag in value:
        if not isinstance(tag, str):
            raise ValidationError(_("All tags must be strings."))
        if not (1 <= len(tag) <= 50):
            raise ValidationError(_("Each tag must be between 1 and 50 characters long."))


class File(BaseModel):
    """
    Represents a file stored in the system.
    """
    # --- Core Fields ---
    name = models.CharField(
        _("Original Filename"),
        max_length=255,
        validators=[validate_no_path_separators],
    )
    display_name = models.CharField(
        _("Display name"),
        max_length=255,
        blank=True,
        null=True,
    )
    description = models.TextField(
        _("Description"),
        max_length=1000,
        blank=True,
        null=True,
    )
    mime_type = models.CharField(
        _("MIME type"),
        max_length=255,
    )
    size = models.PositiveIntegerField(
        _("Size"),
        validators=[
            MinValueValidator(1),
            MaxValueValidator(104857600)  # 100MB
        ],
    )
    hash = models.CharField(
        _("SHA-256 hash"),
        max_length=64,
        validators=[
            RegexValidator(r'^[a-f0-9]{64}$', _("Invalid SHA-256 hash format."))
        ],
    )
    file = models.FileField(
        _("File"),
        upload_to='files/',
    )
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.PROTECT,
        related_name='files',
        verbose_name=_("organization")
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='uploaded_files',
        verbose_name=_("uploaded by")
    )

    # --- Versioning ---
    version = models.PositiveIntegerField(
        _("Version"), default=1, validators=[MinValueValidator(1)]
    )
    parent_file = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="versions",
        verbose_name=_("parent file")
    )

    # --- Flags and Metadata ---
    is_public = models.BooleanField(_("Is public"), default=False,)
    metadata = models.JSONField(_("Metadata"), null=True, blank=True, default=dict)
    tags = models.JSONField(_("Gags"), default=list, validators=[validate_tags],)

    class Meta:
        verbose_name = _("file")
        verbose_name_plural = _("files")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', 'name']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['organization', 'name'], name='unique_file_in_organization')
        ]

    def __str__(self):
        return self.name
