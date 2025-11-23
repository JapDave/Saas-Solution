from __future__ import annotations

import json
from typing import Any, Dict

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

MAX_FLOW_CONFIGURATION_BYTES = 100 * 1024  # 100 KB
MAX_FLOW_JSON_BYTES = 10 * 1024 * 1024  # 10 MB
DEFAULT_VIEWPORT = {"x": 0, "y": 0, "zoom": 1.0}


def _serialized_size(value: Any) -> int:
    try:
        payload = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError) as exc:  # pragma: no cover - explicit rethrow
        raise ValidationError(_("Value must be JSON serializable.")) from exc
    return len(payload.encode("utf-8"))


def validate_flow_configurations(configurations: Any) -> Dict[str, Any]:
    """Ensure configurations are a JSON object within the size budget."""

    if configurations in (None, ""):
        return {}
    if not isinstance(configurations, dict):
        raise ValidationError({"flow_configurations": _("flowConfigurations must be an object.")})
    if _serialized_size(configurations) > MAX_FLOW_CONFIGURATION_BYTES:
        raise ValidationError(
            {"flow_configurations": _("flowConfigurations must be smaller than 100KB.")},
        )
    return configurations


def _validate_nodes(nodes: Any):
    if not isinstance(nodes, list) or not nodes:
        raise ValidationError({"flow_json": _("flowJSON.nodes must contain at least one node.")})
    for node in nodes:
        if not isinstance(node, dict):
            raise ValidationError({"flow_json": _("Each node must be an object.")})
        if not node.get("id"):
            raise ValidationError({"flow_json": _("Each node must include an id.")})


def validate_flow_json(flow_json: Any) -> Dict[str, Any]:
    """Validate the flowJSON payload for basic structural requirements."""

    if not isinstance(flow_json, dict):
        raise ValidationError({"flow_json": _("flowJSON must be an object.")})

    nodes = flow_json.get("nodes")
    _validate_nodes(nodes)

    edges = flow_json.get("edges") or []
    if not isinstance(edges, list):
        raise ValidationError({"flow_json": _("flowJSON.edges must be a list.")})

    viewport = flow_json.get("viewport") or DEFAULT_VIEWPORT
    if not isinstance(viewport, dict):
        raise ValidationError({"flow_json": _("flowJSON.viewport must be an object.")})

    payload = {
        "nodes": nodes,
        "edges": edges,
        "viewport": viewport,
    }

    for key in ("metadata", "name", "description"):
        if key in flow_json:
            payload[key] = flow_json[key]

    if _serialized_size(payload) > MAX_FLOW_JSON_BYTES:
        raise ValidationError({"flow_json": _("flowJSON must be smaller than 10MB.")})

    return payload


__all__ = [
    "validate_flow_configurations",
    "validate_flow_json",
]

