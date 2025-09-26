# # apps/users/models.py
from __future__ import annotations
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.db.models.functions import Lower
from django.conf import settings

from apps.common.models import BaseModel  # safe base (no FKs)

def _email_has_allowed_system_domain(email: str) -> bool:
    allowed = {
        d.strip().lower()
        for d in getattr(settings, "SYSTEM_EMAIL_DOMAINS", "hudhud.ai").split(",")
        if d.strip()
    } or {"hudhud.ai"}
    return bool(email and "@" in email and email.split("@", 1)[1].lower() in allowed)

class UserManager(BaseUserManager):
    use_in_migrations = True

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
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if not _email_has_allowed_system_domain(email):
            raise ValueError("Superuser must use an allowed system email domain")
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)

class User(BaseModel, AbstractBaseUser, PermissionsMixin):
    """
    Custom user:
      - Email is username (unique; case-insensitive uniqueness).
      - Soft delete via BaseModel.deleted_at (manager hides deleted).
      - BaseModel.is_active doubles as Django's is_active flag.
      - NO additional FKs here.
    """
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=100, blank=True, default="")
    is_staff = models.BooleanField(default=False, db_index=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        db_table = "users_user"
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
        if self.full_name and len(self.full_name) > 100:
            raise ValidationError({"full_name": _("full_name must be ≤ 100 characters.")})


    def __str__(self):
        return self.email
