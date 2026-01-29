from __future__ import annotations

import re

from django.conf import settings
from django.contrib.auth.password_validation import MinimumLengthValidator
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from apps.common.exceptions import PASSWORD_POLICY_VIOLATION


class ComplexityValidator:
    """
    Enforces configurable complexity rules from ENVIRONMENT-BASELINE.md.
    """

    def __init__(self):
        self.min_lower = getattr(settings, "PASSWORD_MIN_SMALL_LETTERS", 1)
        self.min_upper = getattr(settings, "PASSWORD_MIN_CAPITAL_LETTERS", 1)
        self.min_numbers = getattr(settings, "PASSWORD_MIN_NUMBERS", 1)
        self.min_special = getattr(settings, "PASSWORD_MIN_SPECIAL_CHARACTERS", 1)
        self.min_length_validator = MinimumLengthValidator(min_length=8)

    def validate(self, password, user=None):
        errors = []
        try:
            self.min_length_validator.validate(password, user=user)
        except ValidationError as exc:
            errors.extend(exc.error_list)

        counts = {
            "lower": len(re.findall(r"[a-z]", password or "")),
            "upper": len(re.findall(r"[A-Z]", password or "")),
            "digit": len(re.findall(r"[0-9]", password or "")),
            "special": len(re.findall(r"[^A-Za-z0-9]", password or "")),
        }
        if counts["lower"] < self.min_lower:
            errors.append(ValidationError(_("Password must contain at least %(min)d lowercase letter(s)."), params={"min": self.min_lower}))
        if counts["upper"] < self.min_upper:
            errors.append(ValidationError(_("Password must contain at least %(min)d uppercase letter(s)."), params={"min": self.min_upper}))
        if counts["digit"] < self.min_numbers:
            errors.append(ValidationError(_("Password must contain at least %(min)d number(s)."), params={"min": self.min_numbers}))
        if counts["special"] < self.min_special:
            errors.append(ValidationError(_("Password must contain at least %(min)d special character(s)."), params={"min": self.min_special}))

        # Similarity checks
        lower_pwd = (password or "").lower()
        similarity_sources = []
        if user:
            if getattr(user, "full_name", None):
                similarity_sources.append(str(user.full_name).lower())
            if getattr(user, "email", None):
                similarity_sources.append(str(user.email).lower())
            try:
                memberships = (
                    user.memberships.select_related("organization__account")
                    if hasattr(user, "memberships")
                    else []
                )
                for membership in memberships:
                    org = getattr(membership, "organization", None)
                    if org and getattr(org, "name", None):
                        similarity_sources.append(str(org.name).lower())
                    account = getattr(org, "account", None) if org else None
                    if account and getattr(account, "name", None):
                        similarity_sources.append(str(account.name).lower())
            except Exception:
                # If user isn't fully loaded, skip org/account similarity
                pass
        for source in similarity_sources:
            if source and source in lower_pwd:
                errors.append(ValidationError(_("Password is too similar to user information.")))

        if errors:
            raise ValidationError(
                [{"code": PASSWORD_POLICY_VIOLATION, "message": err.message % (err.params or {})} for err in errors]
            )

    def get_help_text(self):
        return _(
            "Password must be at least 8 characters and include "
            f"{self.min_lower} lowercase, {self.min_upper} uppercase, "
            f"{self.min_numbers} number(s), {self.min_special} special character(s)."
        )
