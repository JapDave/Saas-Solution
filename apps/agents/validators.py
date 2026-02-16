from __future__ import annotations

import uuid
from typing import Any, Iterable

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.utils.translation import gettext_lazy as _

from apps.common.exceptions import (
    CustomError,
    DUPLICATE_TOOL,
    INVALID_LLM_CONFIGURATION,
    INVALID_TOOL_CONFIGURATION,
    LLM_NOT_ENABLED,
    LLM_REQUIRED,
    TOOL_NOT_ENABLED,
)
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

_NAME_SPECIALS = set("!*()-#?@/^~.:\u00d8\u0152\u00ef\u00b7\u00bc%&'=+$,[]~")
_DESCRIPTION_SPECIALS = set("!*()-#?@/^~.:\u00d8\u0152\u00ef\u00b7\u00bc%&'=+$,[]~")
_SYSTEM_PROMPT_SPECIALS = set("!*()-#?@/^~.:\u00d8\u0152\u00ef\u00b7\u00bc%&'=+$,[]~{}")


def _validate_allowed_characters(value: str, *, allowed_specials: set[str], field_label: str) -> None:
    for ch in value:
        if ch.isalnum() or ch.isspace() or ch in allowed_specials:
            continue
        raise ValidationError({field_label: _(f"{field_label} contains invalid character: {ch}")})


def validate_agent_name(value: str) -> str:
    if value is None:
        raise ValidationError({"name": _("Name is required.")})
    cleaned = value.strip()
    if not cleaned:
        raise ValidationError({"name": _("Name is required.")})
    if len(cleaned) > 250:
        raise ValidationError({"name": _("Name must be 250 characters or fewer.")})
    _validate_allowed_characters(cleaned, allowed_specials=_NAME_SPECIALS, field_label="name")
    return cleaned


def validate_agent_description(value: str | None) -> str:
    cleaned = (value or "").strip()
    if len(cleaned) > 250:
        raise ValidationError({"description": _("Description must be 250 characters or fewer.")})
    if cleaned:
        _validate_allowed_characters(cleaned, allowed_specials=_DESCRIPTION_SPECIALS, field_label="description")
    return cleaned


def _word_count(value: str) -> int:
    tokens = [chunk for chunk in (value or "").strip().split() if chunk]
    return len(tokens)


def _normalize_system_prompts(value: Any) -> list[str]:
    if value is None:
        raise ValidationError({"systemPrompts": _("systemPrompts is required.")})
    if isinstance(value, list):
        prompts = [str(item) for item in value if item is not None]
    elif isinstance(value, str):
        prompts = [value]
    else:
        raise ValidationError({"systemPrompts": _("systemPrompts must be a string or list of strings.")})
    cleaned = [prompt.strip() for prompt in prompts if prompt and str(prompt).strip()]
    if not cleaned:
        raise ValidationError({"systemPrompts": _("systemPrompts is required.")})
    return cleaned


def validate_system_prompts(value: Any) -> list[str]:
    """Ensure the system prompt stays within the documented word limits."""

    prompts = _normalize_system_prompts(value)
    words = sum(_word_count(prompt) for prompt in prompts)
    # Acceptance tests treat max length as 10,000 characters as well.
    if any(len(prompt) > SYSTEM_PROMPT_MAX_WORDS for prompt in prompts):
        raise ValidationError(
            _("systemPrompts must contain between %(min)d and %(max)d words."),
            params={"min": SYSTEM_PROMPT_MIN_WORDS, "max": SYSTEM_PROMPT_MAX_WORDS},
        )
    if words < SYSTEM_PROMPT_MIN_WORDS or words > SYSTEM_PROMPT_MAX_WORDS:
        raise ValidationError(
            _("systemPrompts must contain between %(min)d and %(max)d words."),
            params={"min": SYSTEM_PROMPT_MIN_WORDS, "max": SYSTEM_PROMPT_MAX_WORDS},
        )
    for prompt in prompts:
        _validate_allowed_characters(prompt, allowed_specials=_SYSTEM_PROMPT_SPECIALS, field_label="systemPrompts")
    return prompts


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


def validate_llm_configuration(value: Any, *, organization, raise_custom_error: bool = False) -> dict:
    """Validate agent LLM configuration payload."""

    if not isinstance(value, dict):
        if raise_custom_error:
            raise CustomError(code=INVALID_LLM_CONFIGURATION, status_code=400, detail="llmConfiguration must be an object.")
        raise ValidationError(_("llmConfiguration must be an object."))

    model_key = value.get("modelKey") or value.get("model_key")
    provider = value.get("modelProvider") or value.get("model_provider")
    configuration = value.get("configuration")
    if configuration is None:
        configuration = {
            key: val
            for key, val in value.items()
            if key not in {"modelKey", "model_key", "modelProvider", "model_provider"}
        }

    if not model_key or not isinstance(model_key, str):
        if raise_custom_error:
            raise CustomError(code=LLM_REQUIRED, status_code=400, detail="modelKey is required.")
        raise ValidationError({"modelKey": _("modelKey is required.")})
    definition = get_llm_definition(model_key)
    if not definition:
        if raise_custom_error:
            raise CustomError(code=INVALID_LLM_CONFIGURATION, status_code=400, detail=f"Unknown LLM key {model_key}.")
        raise ValidationError({"modelKey": _("Unknown LLM key %(key)s.") % {"key": model_key}})
    if provider and provider != definition.provider:
        if raise_custom_error:
            raise CustomError(
                code=INVALID_LLM_CONFIGURATION,
                status_code=400,
                detail=f"modelProvider must be {definition.provider}.",
            )
        raise ValidationError({"modelProvider": _("modelProvider must be %(expected)s.") % {"expected": definition.provider}})
    if configuration is None or not isinstance(configuration, dict):
        if raise_custom_error:
            raise CustomError(code=INVALID_LLM_CONFIGURATION, status_code=400, detail="configuration must be an object.")
        raise ValidationError({"configuration": _("configuration must be an object.")})

    if not _ensure_enabled_llm(organization, model_key):
        if raise_custom_error:
            raise CustomError(code=LLM_NOT_ENABLED, status_code=400, detail=f"LLM {model_key} is not enabled for this organization.")
        raise ValidationError({"modelKey": _("LLM %(key)s is not enabled for this organization.") % {"key": model_key}})

    allowed_fields = set(definition.parameters.keys())
    try:
        _reject_unknown_fields(configuration, allowed_fields, "LLM configuration")
    except ValidationError as exc:
        if raise_custom_error:
            raise CustomError(code=INVALID_LLM_CONFIGURATION, status_code=400, detail=str(exc)) from exc
        raise

    cleaned_config = {}
    for param_key, rule in definition.parameters.items():
        if param_key not in configuration:
            if rule.required:
                if raise_custom_error:
                    raise CustomError(code=INVALID_LLM_CONFIGURATION, status_code=400, detail=f"{param_key} is required.")
                raise ValidationError({param_key: _("This parameter is required.")})
            continue
        try:
            cleaned_config[param_key] = _validate_parameter(param_key, configuration[param_key], rule)
        except ValidationError as exc:
            if raise_custom_error:
                raise CustomError(code=INVALID_LLM_CONFIGURATION, status_code=400, detail=str(exc)) from exc
            raise

    # Allow additional optional parameters but still coerce if a rule exists
    for param_key, raw_value in configuration.items():
        if param_key in cleaned_config:
            continue
        cleaned_config[param_key] = raw_value

    # Return flattened payload (tests expect params at top-level, not nested under "configuration").
    flattened = {
        "modelKey": definition.key,
        "modelProvider": definition.provider,
    }
    flattened.update(cleaned_config)
    return flattened


def validate_tools_configuration(
    value: Any,
    *,
    organization,
    raise_custom_error: bool = False,
    allow_incomplete: bool = False,
) -> list[dict]:
    if value in (None, []):
        return []
    if isinstance(value, dict) and "tools" in value:
        value = value.get("tools") or []
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
        if raise_custom_error:
            raise CustomError(code=INVALID_TOOL_CONFIGURATION, status_code=400, detail="toolsConfiguration must be an array.")
        raise ValidationError(_("toolsConfiguration must be an array."))

    seen_keys: set[str] = set()
    cleaned: list[dict] = []
    for entry in value:
        if not isinstance(entry, dict):
            if raise_custom_error:
                raise CustomError(code=INVALID_TOOL_CONFIGURATION, status_code=400, detail="Each tool entry must be an object.")
            raise ValidationError(_("Each tool entry must be an object."))
        tool_key = entry.get("toolKey") or entry.get("tool_key")
        configuration = entry.get("configuration") or {}
        if not tool_key or not isinstance(tool_key, str):
            if raise_custom_error:
                raise CustomError(code=INVALID_TOOL_CONFIGURATION, status_code=400, detail="toolKey is required for each tool.")
            raise ValidationError({"toolKey": _("toolKey is required for each tool.")})
        if tool_key in seen_keys:
            if raise_custom_error:
                raise CustomError(code=DUPLICATE_TOOL, status_code=400, detail=f"Duplicate tool {tool_key} not allowed.")
            raise ValidationError({"toolKey": _("Duplicate tool %(key)s not allowed.") % {"key": tool_key}})
        seen_keys.add(tool_key)

        tool_def = get_tool_definition(tool_key)
        if not tool_def:
            if raise_custom_error:
                raise CustomError(code=INVALID_TOOL_CONFIGURATION, status_code=400, detail=f"Unknown tool key {tool_key}.")
            raise ValidationError({"toolKey": _("Unknown tool key %(key)s.") % {"key": tool_key}})
        if not isinstance(configuration, dict):
            if raise_custom_error:
                raise CustomError(
                    code=INVALID_TOOL_CONFIGURATION,
                    status_code=400,
                    detail=f"configuration must be an object for tool {tool_key}.",
                )
            raise ValidationError({"configuration": _("configuration must be an object for tool %(key)s.") % {"key": tool_key}})
        if not _ensure_enabled_tool(organization, tool_key):
            if raise_custom_error:
                raise CustomError(code=TOOL_NOT_ENABLED, status_code=400, detail=f"Tool {tool_key} is not enabled for this organization.")
            raise ValidationError({"toolKey": _("Tool %(key)s is not enabled for this organization.") % {"key": tool_key}})
        allowed_fields = set(tool_def.parameters.keys())
        try:
            _reject_unknown_fields(configuration, allowed_fields, f"tool {tool_key}")
        except ValidationError as exc:
            if raise_custom_error:
                raise CustomError(code=INVALID_TOOL_CONFIGURATION, status_code=400, detail=str(exc)) from exc
            raise

        cleaned_config = {}
        for param_key, rule in tool_def.parameters.items():
            if param_key not in configuration:
                if rule.required and not allow_incomplete:
                    if raise_custom_error:
                        raise CustomError(
                            code=INVALID_TOOL_CONFIGURATION,
                            status_code=400,
                            detail=f"{param_key} is required for {tool_key}.",
                        )
                    raise ValidationError({param_key: _("This parameter is required for %(tool)s.") % {"tool": tool_key}})
                continue
            try:
                cleaned_config[param_key] = _validate_parameter(param_key, configuration[param_key], rule)
            except ValidationError as exc:
                if raise_custom_error:
                    raise CustomError(code=INVALID_TOOL_CONFIGURATION, status_code=400, detail=str(exc)) from exc
                raise

        for param_key, param_value in configuration.items():
            if param_key in cleaned_config:
                continue
            cleaned_config[param_key] = param_value

        if tool_def.key == "kb_retriever":
            collection_id = cleaned_config.get("collection_id")
            if collection_id:
                exists = Collection.objects.filter(uuid=collection_id, organization=organization).exists()
                if not exists:
                    if raise_custom_error:
                        raise CustomError(code=INVALID_TOOL_CONFIGURATION, status_code=400, detail="Referenced collection does not exist.")
                    raise ValidationError({"collection_id": _("Referenced collection does not exist.")})

        cleaned.append({
            "toolKey": tool_def.key,
            "configuration": cleaned_config,
        })
    return cleaned
