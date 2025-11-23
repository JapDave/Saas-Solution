"""Helpers for loading the canonical LLM/tool schemas from the requirements repo."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from django.conf import settings


LLM_DEFINITIONS_PATH = Path(settings.BASE_DIR) / "Business-Requirements" / "PRODUCT-MODULES" / "llms-list.json"
TOOL_DEFINITIONS_PATH = Path(settings.BASE_DIR) / "Business-Requirements" / "PRODUCT-MODULES" / "tools-list.json"


@dataclass(frozen=True)
class ParameterRule:
    type: str
    required: bool = True
    minimum: float | None = None
    maximum: float | None = None
    choices: Iterable[Any] | None = None
    format: str | None = None


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
    return ParameterRule(
        type=(field.get("type") or "string").lower(),
        required=field.get("required", False),
        minimum=validation.get("min"),
        maximum=validation.get("max"),
        choices=choices,
        format=validation.get("format"),
    )


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Definition file missing: {path}")
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=1)
def _load_llm_definitions() -> Dict[str, LLMDefinition]:
    payload = _load_json(LLM_DEFINITIONS_PATH)
    definitions: Dict[str, LLMDefinition] = {}
    for entry in payload.get("llms", []):
        config = entry.get("modelConfiguration") or {}
        parameters = {name: _build_parameter_rule(field) for name, field in config.items()}
        provider = entry.get("modelProvider", "")
        requires_hosted = provider.lower().startswith("hudhud")
        definition = LLMDefinition(
            key=entry["modelKey"],
            provider=provider,
            display_name=entry.get("displayName", entry["modelKey"]),
            description=entry.get("description", ""),
            raw=entry,
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
