from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

PATH_PARAM_PATTERN = re.compile(r"{([a-zA-Z0-9_]+)}")
VALID_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
PARAMETER_TYPES = {"path", "query", "body"}


def _ensure_json_serializable(value: Any, field: str):
    try:
        json.dumps(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError({field: _("Value must be JSON serializable.")}) from exc


def _validate_headers(headers: Any) -> List[Dict[str, str]]:
    if headers in (None, "", []):
        return []
    if not isinstance(headers, list):
        raise ValidationError({"headers": _("Headers must be a list.")})
    normalized = []
    for header in headers:
        if not isinstance(header, dict):
            raise ValidationError({"headers": _("Each header must be an object.")})
        key = (header.get("key") or "").strip()
        value = (header.get("value") or "").strip()
        if not key:
            raise ValidationError({"headers": _("Header key is required.")})
        normalized.append({"key": key, "value": value})
    return normalized


def _validate_parameters(parameters: Any) -> List[Dict[str, Any]]:
    if parameters in (None, "", []):
        return []
    if not isinstance(parameters, list):
        raise ValidationError({"parameters": _("parameters must be a list.")})
    normalized = []
    for param in parameters:
        if not isinstance(param, dict):
            raise ValidationError({"parameters": _("Each parameter must be an object.")})
        key = (param.get("key") or "").strip()
        display = (param.get("name") or "").strip()
        param_type = (param.get("type") or "").lower()
        if not key:
            raise ValidationError({"parameters": _("Each parameter requires a key.")})
        if param_type not in PARAMETER_TYPES:
            raise ValidationError({"parameters": _(f"Invalid parameter type for {key}.")})
        normalized.append(
            {
                "key": key,
                "name": display or key,
                "type": param_type,
                "required": bool(param.get("required", False)),
                "description": (param.get("description") or "").strip(),
            }
        )
    return normalized


def _validate_response_mappings(mappings: Any) -> List[Dict[str, str]]:
    if not mappings:
        raise ValidationError({"response_mappings": _("responseMappings are required.")})
    if not isinstance(mappings, list):
        raise ValidationError({"response_mappings": _("responseMappings must be a list.")})
    normalized = []
    for mapping in mappings:
        if not isinstance(mapping, dict):
            raise ValidationError({"response_mappings": _("Each mapping must be an object.")})
        key = (mapping.get("key") or "").strip()
        name = (mapping.get("name") or "").strip() or key
        json_path = (mapping.get("jsonPath") or "").strip()
        if not key or not json_path:
            raise ValidationError({"response_mappings": _("Each mapping requires key and jsonPath.")})
        normalized.append({"key": key, "name": name, "jsonPath": json_path})
    return normalized


def _validate_url_placeholders(url: str, parameters: List[Dict[str, Any]]):
    placeholders = PATH_PARAM_PATTERN.findall(url or "")
    path_params = {param["key"] for param in parameters if param["type"] == "path"}
    missing = {placeholder for placeholder in placeholders if placeholder not in path_params}
    if missing:
        raise ValidationError(
            {"url": _(f"Missing path parameters for placeholders: {', '.join(sorted(missing))}.")}
        )


def validate_api_integration(data: Dict[str, Any]) -> Dict[str, Any]:
    url = (data.get("url") or "").strip()
    if not url:
        raise ValidationError({"url": _("URL is required for API integrations.")})
    method = (data.get("method") or "").upper()
    if method not in VALID_METHODS:
        raise ValidationError({"method": _("Invalid HTTP method.")})

    headers = _validate_headers(data.get("headers"))
    parameters = _validate_parameters(data.get("parameters"))
    response_mappings = _validate_response_mappings(data.get("response_mappings"))
    request_body = data.get("request_body") or ""
    if request_body:
        if not isinstance(request_body, str):
            raise ValidationError({"request_body": _("Request body must be a string template.")})

    _ensure_json_serializable(headers, "headers")
    _ensure_json_serializable(parameters, "parameters")
    _ensure_json_serializable(response_mappings, "response_mappings")
    _validate_url_placeholders(url, parameters)

    return {
        "url": url,
        "method": method,
        "headers": headers,
        "parameters": parameters,
        "request_body": request_body,
        "response_mappings": response_mappings,
    }


def validate_webhook_integration(data: Dict[str, Any]) -> Dict[str, Any]:
    response_mappings = _validate_response_mappings(data.get("response_mappings"))
    sample_payload = data.get("sample_payload") or {}
    if sample_payload not in ({}, None):
        if not isinstance(sample_payload, (dict, list)):
            raise ValidationError({"sample_payload": _("Sample payload must be an object or array.")})
        _ensure_json_serializable(sample_payload, "sample_payload")
    return {
        "response_mappings": response_mappings,
        "sample_payload": sample_payload or {},
    }


__all__ = [
    "validate_api_integration",
    "validate_webhook_integration",
]

