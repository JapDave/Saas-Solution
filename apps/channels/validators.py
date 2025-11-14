
from __future__ import annotations

import re
import secrets
from typing import Any, Dict

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.utils.translation import gettext_lazy as _

from apps.channels.definitions import CHANNEL_CONFIGURATION_SCHEMAS, CHANNEL_TYPE_WEB_CHAT

url_validator = URLValidator()
E164_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")
HEX_COLOR_PATTERN = re.compile(r"^#(?:[0-9a-fA-F]{3}){1,2}$")
HANDLE_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,500}$")
LANGUAGE_CODE_PATTERN = re.compile(r"^[a-z]{2}$")

SYSTEM_MANAGED_FIELDS = {"whatsappToken", "whatsappApprovalStatus"}


def _validate_color(value: str) -> None:
    if HEX_COLOR_PATTERN.match(value):
        return
    if value.lower() in {"black", "white", "red", "green", "blue", "yellow", "orange", "purple", "gray"}:
        return
    if value.lower().startswith("rgb"):
        return
    raise ValidationError(_("Must be a valid CSS color."))


def _validate_language_code(code: str) -> None:
    if not LANGUAGE_CODE_PATTERN.match(code):
        raise ValidationError(_("Language codes must be ISO 639-1 two-letter values."))


def _validate_supported_languages(field: str, values: Any) -> list[str]:
    if not isinstance(values, (list, tuple)) or not values:
        raise ValidationError({field: _("Must supply at least one language code.")})
    cleaned = []
    for entry in values:
        if not isinstance(entry, str):
            raise ValidationError({field: _("Language codes must be strings.")})
        entry = entry.strip().lower()
        _validate_language_code(entry)
        cleaned.append(entry)
    return cleaned


def _validate_phone_number(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError(_("Phone number must be a string."))
    value = value.strip()
    if not E164_PATTERN.match(value):
        raise ValidationError(_("Phone number must use E.164 format (e.g., +1234567890)."))
    return value


def _validate_url(value: str, field: str):
    if not isinstance(value, str):
        raise ValidationError({field: _("Must be a string URL.")})
    value = value.strip()
    try:
        url_validator(value)
    except ValidationError:
        raise ValidationError({field: _("Must be a valid URL.")})
    if len(value) > 500:
        raise ValidationError({field: _("URL cannot exceed 500 characters.")})
    return value


def _validate_handle(value: str):
    if not isinstance(value, str):
        raise ValidationError({"xHandle": _("Handle must be a string.")})
    value = value.strip()
    if not HANDLE_PATTERN.match(value):
        raise ValidationError({"xHandle": _("Handle may only contain letters, numbers, and underscores.")})
    return value


def validate_channel_configuration(channel_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
    if channel_type not in CHANNEL_CONFIGURATION_SCHEMAS:
        raise ValidationError({"channel_type": _("Unsupported channel type.")})
    schema = CHANNEL_CONFIGURATION_SCHEMAS[channel_type]
    cleaned: Dict[str, Any] = {}

    for field_name, rule in schema.items():
        if field_name in SYSTEM_MANAGED_FIELDS:
            # user-supplied values are not permitted
            if field_name in config:
                raise ValidationError({field_name: _("Field is managed by the system.")})
            if rule.default is not None:
                cleaned[field_name] = rule.default
            elif field_name == "whatsappToken":
                cleaned[field_name] = secrets.token_hex(16)
            continue

        if field_name not in config:
            if rule.required:
                if rule.default is not None:
                    cleaned[field_name] = rule.default
                else:
                    raise ValidationError({field_name: _("This field is required.")})
            elif rule.default is not None:
                cleaned[field_name] = rule.default
            continue

        value = config[field_name]
        cleaned[field_name] = _coerce_value(field_name, value, rule.field_type, rule)

    # Copy over optional fields not described in schema (future-proofing)
    for key, value in config.items():
        if key not in cleaned and key not in SYSTEM_MANAGED_FIELDS:
            cleaned[key] = value

    if channel_type == CHANNEL_TYPE_WEB_CHAT:
        languages = cleaned.get("webChatSupportedLanguages", [])
        default_language = cleaned.get("webChatDefaultLanguage")
        if default_language not in languages:
            raise ValidationError(
                {"webChatDefaultLanguage": _("default language must be present in supported languages.")}
            )

    return cleaned


def _coerce_value(field: str, value: Any, field_type: str, rule) -> Any:
    if field_type == "string":
        if not isinstance(value, str):
            raise ValidationError({field: _("Must be a string.")})
        value = value.strip()
        if not value and not rule.allow_blank:
            raise ValidationError({field: _("This field cannot be blank.")})
        if len(value) > 500:
            raise ValidationError({field: _("Must be 500 characters or fewer.")})
        return value
    if field_type == "integer":
        try:
            if isinstance(value, bool):
                raise TypeError
            value = int(value)
        except (TypeError, ValueError):
            raise ValidationError({field: _("Must be an integer.")})
        if rule.minimum is not None and value < rule.minimum:
            raise ValidationError({field: _("Must be greater than or equal to %(min)s.") % {"min": rule.minimum}})
        if rule.maximum is not None and value > rule.maximum:
            raise ValidationError({field: _("Must be less than or equal to %(max)s.") % {"max": rule.maximum}})
        return value
    if field_type == "boolean":
        if not isinstance(value, bool):
            raise ValidationError({field: _("Must be a boolean.")})
        return value
    if field_type == "enum":
        if value not in rule.choices:
            raise ValidationError(
                {field: _("Must be one of: %(choices)s.") % {"choices": ", ".join(map(str, rule.choices or []))}}
            )
        return value
    if field_type == "url":
        return _validate_url(value, field)
    if field_type == "array":
        if not isinstance(value, (list, tuple)):
            raise ValidationError({field: _("Must be an array.")})
        return list(value)
    if field_type == "language_list":
        return _validate_supported_languages(field, value)
    if field_type == "language":
        if not isinstance(value, str):
            raise ValidationError({field: _("Must be a string language code.")})
        value = value.strip().lower()
        _validate_language_code(value)
        return value
    if field_type == "color":
        if not isinstance(value, str):
            raise ValidationError({field: _("Must be a CSS color string.")})
        value = value.strip()
        _validate_color(value)
        return value
    if field_type == "phone":
        return _validate_phone_number(value)
    if field_type == "handle":
        return _validate_handle(value)
    if field_type == "system_string":
        raise ValidationError({field: _("Field is system managed.")})
    raise ValidationError({field: _("Unsupported configuration field.")})
