from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Dict, Optional, Tuple

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.urls import resolve
from django.utils.deprecation import MiddlewareMixin

from apps.common.models import AuditLog


DEFAULT_SENSITIVE_FIELDS = frozenset({"password", "token", "secret", "logo_url"})


@lru_cache(maxsize=1)
def _sensitive_fields() -> frozenset[str]:
    """Return the configured set of sensitive payload keys that must be masked."""

    configured = getattr(settings, "AUDIT_LOG_SENSITIVE_FIELDS", None)
    if not configured:
        return DEFAULT_SENSITIVE_FIELDS

    if isinstance(configured, (set, frozenset)):
        return frozenset(str(field) for field in configured)
    if isinstance(configured, (list, tuple)):
        return frozenset(str(field) for field in configured)

    return DEFAULT_SENSITIVE_FIELDS


def _get_client_ip(request: HttpRequest) -> str:
    """Best-effort resolution of the originating client IP address."""

    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.META.get("REMOTE_ADDR", "") or ""


def _try_parse_json_body(request: HttpRequest) -> Optional[Dict[str, Any]]:
    """Parse the request body as JSON when possible, returning ``None`` otherwise."""

    content_type = (request.META.get("CONTENT_TYPE") or "").lower()
    if "application/json" not in content_type:
        return None
    try:
        raw_body = request.body
        if isinstance(raw_body, (bytes, bytearray)):
            raw_body = raw_body.decode("utf-8")
        text = str(raw_body or "")
        return json.loads(text) if text else None
    except Exception:
        return None


def _mask_payload(data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Mask configured sensitive keys within a JSON payload."""

    if not isinstance(data, dict):
        return None
    sensitive = _sensitive_fields()
    return {key: ("***" if key in sensitive else value) for key, value in data.items()}


class AuditLogMiddleware(MiddlewareMixin):
    """Persist a request/response audit trail for API calls."""

    _WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        """Record the request/response metadata while allowing the response to continue."""

        method = request.method.upper()
        try:
            match = resolve(request.path_info)
            view_name = f"{match.func.__module__}.{getattr(match.func, '__name__', '')}"
            app_label, model, action = self._infer_ama(match, request.path, method)
            object_id = self._infer_object_id(match)
        except Exception:
            view_name, app_label, model, action, object_id = "", "", "", "", ""

        payload = (
            _mask_payload(_try_parse_json_body(request))
            if method in self._WRITE_METHODS
            else None
        )

        status_code = int(getattr(response, "status_code", 0))
        try:
            AuditLog.objects.create(
                user=(request.user if getattr(request, "user", None) and request.user.is_authenticated else None),
                method=method,
                path=request.path,
                view=view_name[:255] if view_name else "",
                app_label=app_label[:63],
                model=model[:63],
                action=action[:31],
                object_id=str(object_id or "")[:63],
                status_code=status_code,
                success=200 <= status_code < 400,
                ip_addr=_get_client_ip(request) or None,
                extra={"payload": payload} if payload else {},
            )
        except Exception:
            pass

        return response

    def _infer_ama(self, match, path: str, method: str) -> Tuple[str, str, str]:
        """Infer ``(app_label, model, action)`` best-effort from the path/method pair."""

        lower_path = (path or "").lower()
        if "/organizations" in lower_path:
            return self._map_action("organizations", "organization", lower_path, method)
        if "/accounts" in lower_path:
            return self._map_action("accounts", "account", lower_path, method)
        return "", "", method.lower()

    @staticmethod
    def _map_action(app: str, model: str, path: str, method: str) -> Tuple[str, str, str]:
        """Translate the HTTP method (and path nuance) into an audit action."""

        if method == "POST":
            action = "assign_owner" if any(segment in path for segment in ("/assign-owner", "/owner/assign")) else "create"
        elif method in {"PUT", "PATCH"}:
            action = "update"
        elif method == "DELETE":
            action = "delete"
        else:
            action = "read"
        return app, model, action

    @staticmethod
    def _infer_object_id(match) -> str:
        """Return the best-effort identifier (uuid/pk/id) extracted from the resolver match."""

        kwargs = getattr(match, "kwargs", {}) or {}
        return str(kwargs.get("uuid") or kwargs.get("pk") or kwargs.get("id") or "")
