from __future__ import annotations

import json
import logging
from typing import Any, Optional, Tuple

from django.http import HttpRequest, HttpResponse
from django.urls import resolve
from django.utils.deprecation import MiddlewareMixin

from apps.common.audit import (
    clear_audit_context,
    get_client_ip,
    get_audit_context,
    get_trace_context,
    get_user_agent,
    mask_sensitive,
    set_audit_context,
)
from apps.common.models import AuditLog

logger = logging.getLogger(__name__)


def _try_parse_json_body(request: HttpRequest) -> Optional[dict[str, Any]]:
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


def _mask_payload(data: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not isinstance(data, dict):
        return None
    return mask_sensitive(data)


class AuditLogMiddleware(MiddlewareMixin):
    """Persist a request/response audit trail for API calls."""

    _WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    def process_request(self, request: HttpRequest) -> None:
        method = request.method.upper()
        view_name, app_label, model, action, object_id = self._resolve_request(request, method)
        payload = (
            _mask_payload(_try_parse_json_body(request))
            if method in self._WRITE_METHODS
            else None
        )
        trace_id, span_id = get_trace_context()
        user = request.user if getattr(request, "user", None) and request.user.is_authenticated else None
        try:
            audit_log = AuditLog.objects.create(
                user=user,
                method=method,
                path=request.path,
                view=view_name[:255] if view_name else "",
                app_label=app_label[:63],
                model=model[:63],
                action=action[:31],
                object_id=str(object_id or "")[:63],
                status_code=0,
                success=False,
                ip_addr=get_client_ip(request) or None,
                user_agent=get_user_agent(request) or None,
                trace_id=trace_id,
                span_id=span_id,
                extra={"payload": payload} if payload else {},
            )
        except Exception:
            audit_log = None
            logger.exception("Failed to create audit log entry.")

        set_audit_context(
            audit_log=audit_log,
            user=user,
            request=request,
            trace_id=trace_id,
            span_id=span_id,
        )

    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        status_code = int(getattr(response, "status_code", 0))
        current = get_audit_context().audit_log

        if current:
            try:
                # back-fill user if authenticated and missing
                req_user = getattr(request, "user", None)
                if req_user and getattr(req_user, "is_authenticated", False) and not current.user_id:
                    current.user = req_user
                current.status_code = status_code
                current.success = 200 <= status_code < 400
                current._allow_update = True
                update_fields = ["status_code", "success"]
                if current.user_id:
                    update_fields.append("user")
                current.save(update_fields=update_fields)
            except Exception:
                logger.exception("Failed to finalize audit log entry.")
        else:
            method = request.method.upper()
            view_name, app_label, model, action, object_id = self._resolve_request(request, method)
            trace_id, span_id = get_trace_context()
            user = request.user if getattr(request, "user", None) and request.user.is_authenticated else None
            try:
                AuditLog.objects.create(
                    user=user,
                    method=method,
                    path=request.path,
                    view=view_name[:255] if view_name else "",
                    app_label=app_label[:63],
                    model=model[:63],
                    action=action[:31],
                    object_id=str(object_id or "")[:63],
                    status_code=status_code,
                    success=200 <= status_code < 400,
                    ip_addr=get_client_ip(request) or None,
                    user_agent=get_user_agent(request) or None,
                    trace_id=trace_id,
                    span_id=span_id,
                    extra={},
                )
            except Exception:
                logger.exception("Failed to create fallback audit log entry.")

        clear_audit_context()
        return response

    def process_exception(self, request: HttpRequest, exception: Exception) -> None:
        clear_audit_context()

    def _resolve_request(
        self,
        request: HttpRequest,
        method: str,
    ) -> Tuple[str, str, str, str, str]:
        try:
            match = resolve(request.path_info)
            view_name = f"{match.func.__module__}.{getattr(match.func, '__name__', '')}"
            app_label, model, action = self._infer_ama(match, request.path, method)
            object_id = self._infer_object_id(match)
            return view_name, app_label, model, action, object_id
        except Exception:
            return "", "", "", "", ""

    def _infer_ama(self, match, path: str, method: str) -> Tuple[str, str, str]:
        lower_path = (path or "").lower()
        module = getattr(getattr(match, "func", None), "__module__", "") or ""
        app_label = ""
        if module.startswith("apps."):
            parts = module.split(".")
            if len(parts) > 1:
                app_label = parts[1]
        if "/organizations" in lower_path:
            return self._map_action(app_label or "organizations", "Organization", lower_path, method)
        if "/accounts" in lower_path:
            return self._map_action(app_label or "accounts", "Account", lower_path, method)
        return app_label, "", method.lower()

    @staticmethod
    def _map_action(app: str, model: str, path: str, method: str) -> Tuple[str, str, str]:
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
        kwargs = getattr(match, "kwargs", {}) or {}
        return str(kwargs.get("uuid") or kwargs.get("pk") or kwargs.get("id") or "")
