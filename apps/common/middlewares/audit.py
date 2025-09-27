from __future__ import annotations
import json
from typing import Any, Dict, Optional

from django.utils.deprecation import MiddlewareMixin

from django.http import HttpRequest, HttpResponse
from django.urls import resolve
from apps.common.models import AuditLog
from django.conf import settings
from django.contrib.auth import get_user_model

User = get_user_model()


def _get_client_ip(request: HttpRequest) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or ""


def _try_parse_json_body(request: HttpRequest) -> Optional[Dict[str, Any]]:
    ctype = (request.META.get("CONTENT_TYPE") or "").lower()
    if "application/json" not in ctype:
        return None
    try:
        body = request.body.decode("utf-8") if isinstance(request.body, (bytes, bytearray)) else str(request.body or "")
        return json.loads(body) if body else None
    except Exception:
        return None


def _mask(data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(data, dict):
        return None
    sensitive = set(getattr(settings, "AUDIT_LOG_SENSITIVE_FIELDS", ["logo_url", "password", "token", "secret"]))
    masked = {}
    for k, v in data.items():
        if k in sensitive:
            masked[k] = "***"
        else:
            masked[k] = v
    return masked




class AuditLogMiddleware(MiddlewareMixin):
    """
    Logs:
      - user, method, path, status, success
      - resolved view + (best effort) app/model/action
      - masked JSON payload for write ops
    """

    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        # Resolve the view for richer context (best-effort)
        try:
            match = resolve(request.path_info)
            view_name = f"{match.func.__module__}.{getattr(match.func, '__name__', '')}"
            app_label, model, action = self._infer_ama(match, request)
            object_id = self._infer_object_id(match)
        except Exception:
            view_name, app_label, model, action, object_id = "", "", "", "", ""

        payload = _mask(_try_parse_json_body(request)) if request.method in ("POST", "PUT", "PATCH", "DELETE") else None

        try:
            AuditLog.objects.create(
                user=request.user if getattr(request, "user", None) and request.user.is_authenticated else None,
                method=request.method.upper(),
                path=request.path,
                view=view_name[:255] if view_name else "",
                app_label=app_label[:63],
                model=model[:63],
                action=action[:31],
                object_id=str(object_id or "")[:63],
                status_code=int(getattr(response, "status_code", 0)),
                success=200 <= int(getattr(response, "status_code", 0)) < 400,
                ip_addr=_get_client_ip(request) or None,
                extra={"payload": payload} if payload else {},
            )
        except Exception:
            # Never break the response on audit failures
            pass

        return response

    # ---------- inference helpers ----------

    def _infer_ama(self, match, request: HttpRequest) -> tuple[str, str, str]:
        """
        Try to infer (app_label, model, action) from URL + method.
        Designed to be generic for DRF ViewSets following /api/<model> routes.
        """
        path = request.path.lower()
        method = request.method.upper()

        if "/organizations" in path:
            app, model = "organizations", "organization"
            if method == "POST":
                action = "create"
                if any(seg in path for seg in ["/assign-owner", "/owner/assign"]):
                    action = "assign_owner"
            elif method in ("PUT", "PATCH"):
                action = "update"
            elif method == "DELETE":
                action = "delete"
            else:
                action = "read"
        elif "/accounts" in path:
            app, model = "accounts", "account"
            if method == "POST":
                action = "create"
            elif method in ("PUT", "PATCH"):
                action = "update"
            elif method == "DELETE":
                action = "delete"
            else:
                action = "read"
        else:
            app, model, action = "", "", method.lower()

        return app, model, action

    def _infer_object_id(self, match) -> str:
        """
        Best-effort ID (supports pk or uuid kwarg names).
        """
        kwargs = getattr(match, "kwargs", {}) or {}
        return str(kwargs.get("uuid") or kwargs.get("pk") or kwargs.get("id") or "")
