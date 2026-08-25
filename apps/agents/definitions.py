"""Helpers for loading the canonical LLM/tool schemas from the requirements repo."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from django.conf import settings

from apps.llms.models import LLMDefinition as LLMDefinitionModel


TOOL_DEFINITIONS_PATH = Path(settings.BASE_DIR) / "apps" / "tools" / "fixtures" / "tools-list.json"


@dataclass(frozen=True)
class ParameterRule:
    type: str
    required: bool = True
    minimum: float | None = None
    maximum: float | None = None
    choices: Iterable[Any] | None = None
    format: str | None = None
    min_items: int | None = None
    max_items: int | None = None
    items: "ParameterRule | None" = None


@dataclass(frozen=True)
class LLMDefinition:
    key: str
    provider: str
    display_name: str
    description: str
    raw: Dict[str, Any]
    requires_hosted_subscription: bool = False
    parameters: Dict[str, ParameterRule] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolDefinition:
    key: str
    display_name: str
    description: str
    raw: Dict[str, Any]
    parameters: Dict[str, ParameterRule] = field(default_factory=dict)


def _build_parameter_rule(field: Dict[str, Any]) -> ParameterRule:
    validation = field.get("validation") or {}
    choices = validation.get("enum") or validation.get("choices")
    items = validation.get("items") or {}
    item_rule = None
    if isinstance(items, dict) and items:
        item_rule = ParameterRule(
            type=(items.get("type") or "string").lower(),
            required=True,
            choices=items.get("enum") or items.get("choices"),
            format=items.get("format"),
        )
    return ParameterRule(
        type=(field.get("type") or "string").lower(),
        required=field.get("required", False),
        minimum=validation.get("min"),
        maximum=validation.get("max"),
        choices=choices,
        format=validation.get("format"),
        min_items=validation.get("minItems"),
        max_items=validation.get("maxItems"),
        items=item_rule,
    )


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Definition file missing: {path}")
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=1)
def _load_llm_definitions() -> Dict[str, LLMDefinition]:
    """Load LLM definitions from the DB only (seed via `seed_llms`)."""
    qs = (
        LLMDefinitionModel.objects.filter(deleted_at__isnull=True, is_active=True)
        .order_by("model_provider", "model_key")
        .values(
            "model_key",
            "model_provider",
            "display_name",
            "description",
            "supported_modalities",
            "max_context_tokens",
            "model_configuration",
        )
    )
    definitions: Dict[str, LLMDefinition] = {}
    for entry in qs:
        config = entry.get("model_configuration") or {}
        parameters = {name: _build_parameter_rule(field) for name, field in config.items()}
        provider = entry.get("model_provider", "")
        requires_hosted = provider.lower().startswith("saas platform")
        raw = {
            "modelKey": entry["model_key"],
            "modelProvider": provider,
            "displayName": entry["display_name"],
            "description": entry.get("description", ""),
            "supportedModalities": entry.get("supported_modalities") or [],
            "maxContextTokens": entry.get("max_context_tokens"),
            "modelConfiguration": config,
        }
        definition = LLMDefinition(
            key=entry["model_key"],
            provider=provider,
            display_name=entry["display_name"],
            description=entry.get("description", ""),
            raw=raw,
            requires_hosted_subscription=requires_hosted,
            parameters=parameters,
        )
        definitions[definition.key] = definition
    return definitions


@lru_cache(maxsize=1)
def _load_tool_definitions() -> Dict[str, ToolDefinition]:
    payload = _load_json(TOOL_DEFINITIONS_PATH)
    definitions: Dict[str, ToolDefinition] = {}
    for entry in payload.get("tools", []):
        config = entry.get("configurationSchema") or {}
        parameters = {name: _build_parameter_rule(field) for name, field in config.items()}
        definition = ToolDefinition(
            key=entry["toolKey"],
            display_name=entry.get("displayName", entry["toolKey"]),
            description=entry.get("description", ""),
            raw=entry,
            parameters=parameters,
        )
        definitions[definition.key] = definition
    return definitions


def get_llm_definition(model_key: str) -> LLMDefinition | None:
    return _load_llm_definitions().get(model_key)


def get_tool_definition(tool_key: str) -> ToolDefinition | None:
    return _load_tool_definitions().get(tool_key)


def list_llm_definitions() -> List[LLMDefinition]:
    return list(_load_llm_definitions().values())


def list_tool_definitions() -> List[ToolDefinition]:
    return list(_load_tool_definitions().values())
