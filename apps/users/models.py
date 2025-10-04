from __future__ import annotations

from typing import Iterable, Sequence

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel


def _email_has_allowed_system_domain(email: str) -> bool:
    allowed = {
        d.strip().lower()
        for d in getattr(settings, "SYSTEM_EMAIL_DOMAINS", "hudhud.ai").split(",")
        if d.strip()
    } or {"hudhud.ai"}
    return bool(email and "@" in email and email.split("@", 1)[1].lower() in allowed)


class UserManager(BaseUserManager):
    use_in_migrations = True

    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)

    def with_deleted(self):
        return super().get_queryset()

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Email must be set")
        email = self.normalize_email(email)
        if (extra_fields.get("is_staff") or extra_fields.get("is_superuser")) and not _email_has_allowed_system_domain(email):
            raise ValueError("Staff/Superuser must use an allowed system email domain")
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        user.full_clean()
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("is_active", True)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        if not _email_has_allowed_system_domain(email):
            raise ValueError("Superuser must use an allowed system email domain")
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class User(BaseModel, AbstractBaseUser, PermissionsMixin):
    """Custom user supporting multi-organization membership and soft delete."""

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=100, blank=True)
    profile_image = models.URLField(blank=True, null=True)
    user_preferences = models.JSONField(default=dict, blank=True)
    is_staff = models.BooleanField(default=False, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="users_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="users_updated",
    )

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: Sequence[str] = []

    class Meta:
        indexes = [
            models.Index(Lower("email"), name="ix_user_email_ci"),
            models.Index(Lower("full_name"), name="ix_user_full_name_ci"),
        ]
        constraints = [
            models.UniqueConstraint(Lower("email"), name="uq_user_email_ci"),
        ]

    def clean(self):
        super().clean()
        if (self.is_staff or self.is_superuser) and not _email_has_allowed_system_domain(self.email):
            raise ValidationError({"email": _("Staff/Superuser must use an allowed system email domain.")})
        name = (self.full_name or "").strip()
        if len(name) > 100:
            raise ValidationError({"full_name": _("full_name must be 100 characters or fewer.")})
        self.full_name = name
        if self.pk:
            existing_email = (
                type(self)
                .objects
                .with_deleted()
                .filter(pk=self.pk)
                .values_list("email", flat=True)
                .first()
            )
            if existing_email and existing_email.lower() != self.email.lower():
                raise ValidationError({"email": _("Email cannot be changed once set.")})
        if self.profile_image:
            if not str(self.profile_image).startswith(("http://", "https://")):
                raise ValidationError({"profile_image": _("Profile image URL must use http or https.")})
        if not isinstance(self.user_preferences, dict):
            raise ValidationError({"user_preferences": _("User preferences must be a JSON object.")})

    def delete(self, using=None, keep_parents=False):
        if self.deleted_at:
            return
        if self.is_active:
            self.is_active = False
            self.save(update_fields=["is_active", "updated_at"])
        super().delete(using=using, keep_parents=keep_parents)
        UserOrganization.all_objects.filter(user=self, deleted_at__isnull=True).update(
            is_active=False,
            deleted_at=timezone.now(),
            updated_at=timezone.now(),
        )

    def restore(self):
        super().restore()
        if not self.is_active:
            self.is_active = True
            self.save(update_fields=["is_active", "updated_at"])

    def __str__(self):
        return self.email


class UserOrganizationQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def active(self):
        return self.alive().filter(is_active=True)


class UserOrganizationManager(models.Manager.from_queryset(UserOrganizationQuerySet)):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class UserOrganization(BaseModel):
    """Join table capturing organization membership metadata."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="memberships_assigned",
    )
    assigned_at = models.DateTimeField(auto_now_add=True, db_index=True)
    permission_keys = models.JSONField(default=list, blank=True)

    objects = UserOrganizationManager()
    all_objects = models.Manager()

    class Meta:
        indexes = [
            models.Index(fields=["user", "organization"], name="ix_user_org_membership"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "organization"],
                condition=models.Q(deleted_at__isnull=True),
                name="uq_active_user_org",
            ),
        ]

    def clean(self):
        super().clean()
        if not self.user.is_active:
            raise ValidationError({"user": _("User must be active to join an organization.")})
        if not isinstance(self.permission_keys, list):
            raise ValidationError({"permission_keys": _("Permissions must be provided as a list of strings.")})
        invalid = [perm for perm in self.permission_keys if not isinstance(perm, str) or not perm.strip()]
        if invalid:
            raise ValidationError({"permission_keys": _("Each permission must be a non-empty string.")})

    def add_permissions(self, permissions: Iterable[str]):
        current = set(self.permission_keys or [])
        for perm in permissions:
            if isinstance(perm, str) and perm.strip():
                current.add(perm)
        self.permission_keys = sorted(current)
        self.save(update_fields=["permission_keys", "updated_at"])
        try:
            from apps.users.services import invalidate_user_permission_cache  # type: ignore
            invalidate_user_permission_cache(self.user_id, self.organization_id)
        except Exception:
            pass

    def remove_permissions(self, permissions: Iterable[str]):
        current = set(self.permission_keys or [])
        for perm in permissions:
            current.discard(perm)
        self.permission_keys = sorted(current)
        self.save(update_fields=["permission_keys", "updated_at"])
        try:
            from apps.users.services import invalidate_user_permission_cache  # type: ignore
            invalidate_user_permission_cache(self.user_id, self.organization_id)
        except Exception:
            pass


    def deactivate(self):
        if self.deleted_at:
            return
        if self.is_active:
            self.is_active = False
            self.save(update_fields=["is_active", "updated_at"])

    def __str__(self):
        return f"{self.user_id} -> {self.organization_id}"

