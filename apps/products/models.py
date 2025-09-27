# std lib
import uuid

# Django/DRF import
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.postgres.fields import ArrayField
from django.core.validators import MinLengthValidator

# Third party lib
from safedelete.models import SafeDeleteModel
from safedelete.models import SOFT_DELETE

# Project imports
from apps.products.validators import (
    validate_uppercase_and_underscores,
    validate_uppercase_only,
)
from apps.common.models import UserDateAbstract


class Product(UserDateAbstract, SafeDeleteModel):
    """Represents a product offering."""

    _safedelete_policy = SOFT_DELETE

    uuid = models.UUIDField(default=uuid.uuid4, editable=False)
    key = models.CharField(_("Key"), max_length=50, unique=True)
    name = models.CharField(_("Name"), max_length=100)
    description = models.CharField(_("Description"), max_length=500)
    available_module_keys = ArrayField(
        models.CharField(max_length=50), size=10, default=list, blank=True,
        verbose_name=_("Available Module Keys")
    )
    target_segments = ArrayField(
        models.CharField(max_length=50), size=10, default=list, blank=True,
        verbose_name=_("Target Segments")
    )
    use_cases = ArrayField(
        models.CharField(max_length=100), size=20, default=list, blank=True,
        verbose_name=_("Use Cases")
    )
    is_active = models.BooleanField(_("Is Active"), default=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("Product")
        verbose_name_plural = _("Products")


class Module(UserDateAbstract, SafeDeleteModel):
    """Represents a module or feature that can be part of a product."""

    _safedelete_policy = SOFT_DELETE

    uuid = models.UUIDField(default=uuid.uuid4, editable=False)
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
    is_active = models.BooleanField(_("Is Active"), default=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("Module")
        verbose_name_plural = _("Modules")
