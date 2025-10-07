# std lib
import uuid

# Django/DRF import
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.postgres.fields import ArrayField
from django.core.validators import MinLengthValidator

# Project imports
from apps.products.validators import (
    validate_uppercase_and_underscores,
    validate_uppercase_only,
)
from apps.common.models import BaseModel


class Product(BaseModel):
    """Represents a product offering."""

    key = models.CharField(_("Key"), max_length=50, unique=True)
    name = models.CharField(_("Name"), max_length=100)
    description = models.CharField(_("Description"), max_length=500)
    target_segments = ArrayField(
        models.CharField(max_length=50), size=10, default=list, blank=True,
        verbose_name=_("Target Segments")
    )
    use_cases = ArrayField(
        models.CharField(max_length=100), size=20, default=list, blank=True,
        verbose_name=_("Use Cases")
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("Product")
        verbose_name_plural = _("Products")


class Module(BaseModel):
    """Represents a module or feature that can be part of a product."""

    key = models.CharField(
        _("Key"),
        max_length=50,
        unique=True,
        validators=[validate_uppercase_and_underscores]
    )  # e.g., "USER_MANAGEMENT"
    code = models.CharField(
        _("Code"),
        max_length=10,
        unique=True,
        validators=[
            MinLengthValidator(2),
            validate_uppercase_only
        ]
    )  # e.g., "UM"
    name = models.CharField(_("Name"), max_length=100)
    description = models.CharField(_("Description"), max_length=500, blank=True)
    subscribable = models.BooleanField(_("Subscribable"), default=True)
    configurable_attributes = models.JSONField(
        _("Configurable Attributes"),
        null=True,
        blank=True
    )
    exposed_permissions = ArrayField(
        models.CharField(max_length=100),
        size=50,
        blank=True,
        default=list,
        verbose_name=_("Exposed Permissions"))
    products = models.ManyToManyField(
        Product,
        related_name="modules",
        verbose_name=_("Products")
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("Module")
        verbose_name_plural = _("Modules")
