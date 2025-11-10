"""
Static LLM and tool definitions for validation.
In production these would likely be loaded from dynamic config or JSON assets,
but we keep them close to the codebase for now so serializers can enforce the
constraints described in the requirements document.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable


@dataclass(frozen=True)
class ParameterRule:
    """Schema rule for a numeric/string/bool parameter."""

    type: str
    required: bool = True
    minimum: float | None = None
    maximum: float | None = None
    choices: Iterable[Any] | None = None


@dataclass(frozen=True)
class LLMDefinition:
    key: str
    provider: str
    display_name: str
    requires_hosted_subscription: bool = False
    parameters: Dict[str, ParameterRule] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolDefinition:
    key: str
    display_name: str
    parameters: Dict[str, ParameterRule] = field(default_factory=dict)


LLM_DEFINITIONS: Dict[str, LLMDefinition] = {
    "gpt-4o-mini": LLMDefinition(
        key="gpt-4o-mini",
        provider="OpenAI",
        display_name="GPT-4o Mini",
        requires_hosted_subscription=True,
        parameters={
            "temperature": ParameterRule(type="float", minimum=0, maximum=1),
            "maxTokens": ParameterRule(type="int", minimum=1, maximum=4000),
            "topP": ParameterRule(type="float", minimum=0, maximum=1),
            "frequencyPenalty": ParameterRule(type="float", minimum=-2, maximum=2, required=False),
            "presencePenalty": ParameterRule(type="float", minimum=-2, maximum=2, required=False),
        },
    ),
    "deepseek-r1": LLMDefinition(
        key="deepseek-r1",
        provider="DeepSeek",
        display_name="DeepSeek Reasoning",
        requires_hosted_subscription=True,
        parameters={
            "temperature": ParameterRule(type="float", minimum=0, maximum=1),
            "maxTokens": ParameterRule(type="int", minimum=1, maximum=8000),
        },
    ),
    "azure-gpt-35": LLMDefinition(
        key="azure-gpt-35",
        provider="AzureOpenAI",
        display_name="Azure GPT 3.5",
        requires_hosted_subscription=False,
        parameters={
            "temperature": ParameterRule(type="float", minimum=0, maximum=1),
            "maxTokens": ParameterRule(type="int", minimum=1, maximum=2000),
            "topP": ParameterRule(type="float", minimum=0, maximum=1, required=False),
        },
    ),
}


TOOL_DEFINITIONS: Dict[str, ToolDefinition] = {
    "kb_retriever": ToolDefinition(
        key="kb_retriever",
        display_name="Knowledge Base Retriever",
        parameters={
            "collection_id": ParameterRule(type="string"),
            "maxResults": ParameterRule(type="int", minimum=1, maximum=50, required=False),
            "similarityThreshold": ParameterRule(type="float", minimum=0, maximum=1, required=False),
        },
    ),
    "calculator": ToolDefinition(
        key="calculator",
        display_name="Expression Calculator",
        parameters={
            "expression": ParameterRule(type="string", required=False),
        },
    ),
}


def get_llm_definition(model_key: str) -> LLMDefinition | None:
    return LLM_DEFINITIONS.get(model_key)


def get_tool_definition(tool_key: str) -> ToolDefinition | None:
    return TOOL_DEFINITIONS.get(tool_key)

