from __future__ import annotations

import uuid
from typing import Any, Iterable

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.utils.translation import gettext_lazy as _

from apps.agents.definitions import (
    list_llm_definitions,
    list_tool_definitions,
    ParameterRule,
    get_llm_definition,
    get_tool_definition,
)
from apps.knowledge_base.models import Collection

SYSTEM_PROMPT_MIN_WORDS = 1
SYSTEM_PROMPT_MAX_WORDS = 10_000


def _word_count(value: str) -> int:
    tokens = [chunk for chunk in (value or "").strip().split() if chunk]
    return len(tokens)


def validate_system_prompts(value: str) -> str:
    """Ensure the system prompt stays within the documented word limits."""

    words = _word_count(value)
    if words < SYSTEM_PROMPT_MIN_WORDS or words > SYSTEM_PROMPT_MAX_WORDS:
        raise ValidationError(
            _("systemPrompts must contain between %(min)d and %(max)d words."),
            params={"min": SYSTEM_PROMPT_MIN_WORDS, "max": SYSTEM_PROMPT_MAX_WORDS},
        )
    return value


def _validate_parameter(key: str, value: Any, rule: ParameterRule) -> Any:
    """Ensure a config parameter respects type/range constraints."""

    if value is None:
        if rule.required:
            raise ValidationError({key: _("This parameter is required.")})
        return value

    expected = (rule.type or "string").lower()
    if expected in {"float", "number"}:
        try:
            value = float(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError({key: _("Must be a number.")}) from exc
    elif expected in {"int", "integer"}:
        try:
            if isinstance(value, bool):
                raise TypeError
            value = int(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError({key: _("Must be an integer.")}) from exc
    elif expected in {"string", "uuid"}:
        if not isinstance(value, str):
            raise ValidationError({key: _("Must be a string.")})
        value = value.strip()
        if not value and rule.required:
            raise ValidationError({key: _("Must be a non-empty string.")})
        if expected == "uuid" or (rule.format == "uuid"):
            try:
                uuid.UUID(value)
            except (TypeError, ValueError) as exc:
                raise ValidationError({key: _("Must be a valid UUID string.")}) from exc
        if rule.format == "url":
            validator = URLValidator()
            try:
                validator(value)
            except Exception as exc:
                raise ValidationError({key: _("Must be a valid URL.")}) from exc
    elif expected == "boolean":
        if not isinstance(value, bool):
            raise ValidationError({key: _("Must be a boolean.")})
    elif expected in {"array", "list"}:
        if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
            raise ValidationError({key: _("Must be an array.")})
        value = list(value)
        if rule.min_items is not None and len(value) < rule.min_items:
            raise ValidationError({key: _("Must contain at least %(min)s items.") % {"min": rule.min_items}})
        if rule.max_items is not None and len(value) > rule.max_items:
            raise ValidationError({key: _("Must contain at most %(max)s items.") % {"max": rule.max_items}})
        if rule.items is not None:
            for item in value:
                _validate_parameter(key, item, rule.items)
    elif expected == "object":
        if not isinstance(value, dict):
            raise ValidationError({key: _("Must be an object.")})
    else:
        raise ValidationError({key: _("Unsupported parameter type %(type)s.") % {"type": rule.type}})

    if rule.minimum is not None and isinstance(value, (int, float)) and value < rule.minimum:
        raise ValidationError({key: _("Must be greater than or equal to %(min)s.") % {"min": rule.minimum}})
    if rule.maximum is not None and isinstance(value, (int, float)) and value > rule.maximum:
        raise ValidationError({key: _("Must be less than or equal to %(max)s.") % {"max": rule.maximum}})
    if rule.choices is not None and value not in rule.choices:
        raise ValidationError({key: _("Must be one of %(choices)s.") % {"choices": ", ".join(map(str, rule.choices))}})
    return value

def _reject_unknown_fields(configuration: dict, allowed: set[str], context: str):
    for key in configuration.keys():
        if key not in allowed:
            raise ValidationError({key: _(f"Unknown field for {context}.")})


def _ensure_enabled_llm(organization, model_key: str):
    from apps.agents.models import OrganizationEnabledLLM

    return OrganizationEnabledLLM.objects.filter(
        organization=organization,
        model_key=model_key,
        disabled_at__isnull=True,
    ).first()


def _ensure_enabled_tool(organization, tool_key: str):
    from apps.agents.models import OrganizationEnabledTool

    return OrganizationEnabledTool.objects.filter(
        organization=organization,
        tool_key=tool_key,
        disabled_at__isnull=True,
    ).first()


def validate_llm_configuration(value: Any, *, organization) -> dict:
    """Validate agent LLM configuration payload."""

    if not isinstance(value, dict):
        raise ValidationError(_("llmConfiguration must be an object."))

    model_key = value.get("modelKey") or value.get("model_key")
    provider = value.get("modelProvider") or value.get("model_provider")
    configuration = value.get("configuration")

    if not model_key or not isinstance(model_key, str):
        raise ValidationError({"modelKey": _("modelKey is required.")})
    definition = get_llm_definition(model_key)
    if not definition:
        raise ValidationError({"modelKey": _("Unknown LLM key %(key)s.") % {"key": model_key}})
    if provider and provider != definition.provider:
        raise ValidationError({"modelProvider": _("modelProvider must be %(expected)s.") % {"expected": definition.provider}})
    if configuration is None or not isinstance(configuration, dict):
        raise ValidationError({"configuration": _("configuration must be an object.")})

    if not _ensure_enabled_llm(organization, model_key):
        raise ValidationError({"modelKey": _("LLM %(key)s is not enabled for this organization.") % {"key": model_key}})

    allowed_fields = set(definition.parameters.keys())
    _reject_unknown_fields(configuration, allowed_fields, "LLM configuration")

    cleaned_config = {}
    for param_key, rule in definition.parameters.items():
        if param_key not in configuration:
            if rule.required:
                raise ValidationError({param_key: _("This parameter is required.")})
            continue
        cleaned_config[param_key] = _validate_parameter(param_key, configuration[param_key], rule)

    # Allow additional optional parameters but still coerce if a rule exists
    for param_key, raw_value in configuration.items():
        if param_key in cleaned_config:
            continue
        cleaned_config[param_key] = raw_value

    return {
        "modelKey": definition.key,
        "modelProvider": definition.provider,
        "configuration": cleaned_config,
    }


def validate_tools_configuration(value: Any, *, organization) -> list[dict]:
    if value in (None, []):
        return []
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
        raise ValidationError(_("toolsConfiguration must be an array."))

    seen_keys: set[str] = set()
    cleaned: list[dict] = []
    for entry in value:
        if not isinstance(entry, dict):
            raise ValidationError(_("Each tool entry must be an object."))
        tool_key = entry.get("toolKey") or entry.get("tool_key")
        configuration = entry.get("configuration") or {}
        if not tool_key or not isinstance(tool_key, str):
            raise ValidationError({"toolKey": _("toolKey is required for each tool.")})
        if tool_key in seen_keys:
            raise ValidationError({"toolKey": _("Duplicate tool %(key)s not allowed.") % {"key": tool_key}})
        seen_keys.add(tool_key)

        tool_def = get_tool_definition(tool_key)
        if not tool_def:
            raise ValidationError({"toolKey": _("Unknown tool key %(key)s.") % {"key": tool_key}})
        if not isinstance(configuration, dict):
            raise ValidationError({"configuration": _("configuration must be an object for tool %(key)s.") % {"key": tool_key}})
        if not _ensure_enabled_tool(organization, tool_key):
            raise ValidationError({"toolKey": _("Tool %(key)s is not enabled for this organization.") % {"key": tool_key}})
        allowed_fields = set(tool_def.parameters.keys())
        _reject_unknown_fields(configuration, allowed_fields, f"tool {tool_key}")

        cleaned_config = {}
        for param_key, rule in tool_def.parameters.items():
            if param_key not in configuration:
                if rule.required:
                    raise ValidationError({param_key: _("This parameter is required for %(tool)s.") % {"tool": tool_key}})
                continue
            cleaned_config[param_key] = _validate_parameter(param_key, configuration[param_key], rule)

        for param_key, param_value in configuration.items():
            if param_key in cleaned_config:
                continue
            cleaned_config[param_key] = param_value

        if tool_def.key == "kb_retriever":
            collection_id = cleaned_config.get("collection_id")
            if collection_id:
                exists = Collection.objects.filter(uuid=collection_id, organization=organization).exists()
                if not exists:
                    raise ValidationError({"collection_id": _("Referenced collection does not exist.")})

        cleaned.append({
            "toolKey": tool_def.key,
            "configuration": cleaned_config,
        })
    return cleaned
