from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class TimeStampedAbstract(models.Model):
    """
    Abstract class for created and updated timestamp fields.
    """

    created_at = models.DateTimeField(_("Date created"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Date updated"), auto_now=True)

    class Meta:
        abstract = True



class TimeStampedAbstract(models.Model):
    """
    Abstract class for created and updated timestamp fields.
    """

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date created")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Date updated")

    class Meta:
        abstract = True


class UpdatedByCreatedByAbstract(models.Model):
    """
    Abstract class for created_by and updated_by fields.
    """

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        verbose_name=_("Created by"),
        related_name="%(app_label)s_%(class)s_created_by",
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        verbose_name=_("Updated by"),
        related_name="%(app_label)s_%(class)s_updated_by",
        null=True,
        blank=True,
    )

    class Meta:
        abstract = True


class UserDateAbstract(TimeStampedAbstract, UpdatedByCreatedByAbstract):
    """
    Abstract class for created, updated, created_by and updated_by fields.
    """

    class Meta:
        abstract = True
