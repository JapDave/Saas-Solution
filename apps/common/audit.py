from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.conf import settings
from django.http import HttpRequest

from apps.common.models import AuditLog

logger = logging.getLogger(__name__)
_thread_local = threading.local()


DEFAULT_SENSITIVE_FIELDS = {
    "password",
    "token",
    "secret",
    "contact_email",
    "api_key",
    "client_secret",
    "access_token",
    "refresh_token",
    "webhook_secret",
    "webhook_token",
    "content",
    "message",
    "body",
    "text",
    "html",
    "notes",
    "comment",
}


@dataclass
class AuditContext:
    audit_log: AuditLog | None = None
    user: Any | None = None
    request: HttpRequest | None = None
    trace_id: str | None = None
    span_id: str | None = None


def set_audit_context(
    *,
    audit_log: AuditLog | None = None,
    user: Any | None = None,
    request: HttpRequest | None = None,
    trace_id: str | None = None,
    span_id: str | None = None,
) -> None:
    _thread_local.context = AuditContext(
        audit_log=audit_log,
        user=user,
        request=request,
        trace_id=trace_id,
        span_id=span_id,
    )


def clear_audit_context() -> None:
    _thread_local.context = AuditContext()


def get_audit_context() -> AuditContext:
    return getattr(_thread_local, "context", AuditContext())


def get_client_ip(request: HttpRequest | None) -> str:
    if not request:
        return ""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.META.get("REMOTE_ADDR", "") or ""


def get_user_agent(request: HttpRequest | None) -> str:
    if not request:
        return ""
    return request.META.get("HTTP_USER_AGENT", "") or ""


def _normalize_sensitive_fields() -> set[str]:
    configured = getattr(settings, "AUDIT_LOG_SENSITIVE_FIELDS", None)
    fields = set(DEFAULT_SENSITIVE_FIELDS)
    if configured:
        if isinstance(configured, (set, frozenset, list, tuple)):
            fields.update(str(item).strip() for item in configured if str(item).strip())
        elif isinstance(configured, str):
            fields.update(item.strip() for item in configured.split(",") if item.strip())
    return {field.lower() for field in fields}


def mask_sensitive(value: Any, *, field_name: str | None = None) -> Any:
    sensitive_fields = _normalize_sensitive_fields()
    if field_name and field_name.lower() in sensitive_fields:
        return "***"
    if isinstance(value, dict):
        return {
            key: mask_sensitive(val, field_name=key)
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [mask_sensitive(item) for item in value]
    return value


def serialize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (list, dict)):
        return value
    return str(value)


def get_trace_context() -> tuple[str | None, str | None]:
    if not getattr(settings, "ENABLE_APM", False):
        return None, None
    provider = (getattr(settings, "APM_PROVIDER", "") or "").upper()
    try:
        if provider == "ELASTIC":
            import elasticapm  # type: ignore

            return elasticapm.get_trace_id(), elasticapm.get_span_id()
        if provider == "DATADOG":
            from ddtrace import tracer  # type: ignore

            span = tracer.current_span()
            if not span:
                return None, None
            return str(span.trace_id), str(span.span_id)
        if provider in {"OTEL", "GCP"}:
            from opentelemetry import trace  # type: ignore

            span = trace.get_current_span()
            if not span:
                return None, None
            ctx = span.get_span_context()
            if not ctx or not ctx.is_valid:
                return None, None
            return f"{ctx.trace_id:032x}", f"{ctx.span_id:016x}"
    except Exception:
        return None, None
    return None, None


def set_apm_context(
    *,
    user_id: Any | None = None,
    organization_id: Any | None = None,
    account_id: Any | None = None,
) -> None:
    if not getattr(settings, "ENABLE_APM", False):
        return
    provider = (getattr(settings, "APM_PROVIDER", "") or "").upper()
    try:
        if provider == "ELASTIC":
            import elasticapm  # type: ignore

            if user_id is not None:
                elasticapm.set_user_context({"id": str(user_id)})
            elasticapm.set_custom_context(
                {
                    "organization_id": str(organization_id) if organization_id else None,
                    "account_id": str(account_id) if account_id else None,
                }
            )
        elif provider == "DATADOG":
            from ddtrace import tracer  # type: ignore

            span = tracer.current_span()
            if span:
                if user_id is not None:
                    span.set_tag("user.id", str(user_id))
                if organization_id is not None:
                    span.set_tag("organization.id", str(organization_id))
                if account_id is not None:
                    span.set_tag("account.id", str(account_id))
        elif provider in {"OTEL", "GCP"}:
            from opentelemetry import trace  # type: ignore

            span = trace.get_current_span()
            if span:
                if user_id is not None:
                    span.set_attribute("user.id", str(user_id))
                if organization_id is not None:
                    span.set_attribute("organization.id", str(organization_id))
                if account_id is not None:
                    span.set_attribute("account.id", str(account_id))
    except Exception:
        return


def log_authorization_decision(
    request: HttpRequest | None,
    *,
    decision: bool,
    permission: str | None = None,
    roles: list[str] | None = None,
    reason: str | None = None,
    resource: dict[str, Any] | None = None,
) -> None:
    try:
        trace_id, span_id = get_trace_context()
        user = getattr(request, "user", None) if request else None
        AuditLog.objects.create(
            user=user if getattr(user, "is_authenticated", False) else None,
            method=getattr(request, "method", "AUTH"),
            path=getattr(request, "path", "") or "",
            view="authorization",
            app_label="authorization",
            model="",
            action="authorize",
            object_id="",
            status_code=200 if decision else 403,
            success=decision,
            ip_addr=get_client_ip(request) or None,
            user_agent=get_user_agent(request) or None,
            trace_id=trace_id,
            span_id=span_id,
            extra={
                "permission": permission,
                "roles": roles or [],
                "reason": reason,
                "resource": resource or {},
            },
        )
    except Exception:
        logger.exception("Failed to log authorization decision.")


def log_audit_access(
    request: HttpRequest | None,
    *,
    action: str,
    query: dict[str, Any] | None = None,
    success: bool = True,
) -> None:
    try:
        trace_id, span_id = get_trace_context()
        user = getattr(request, "user", None) if request else None
        AuditLog.objects.create(
            user=user if getattr(user, "is_authenticated", False) else None,
            method=getattr(request, "method", "GET"),
            path=getattr(request, "path", "") or "",
            view="audit_log_access",
            app_label="common",
            model="AuditLog",
            action=action,
            object_id="",
            status_code=200 if success else 403,
            success=success,
            ip_addr=get_client_ip(request) or None,
            user_agent=get_user_agent(request) or None,
            trace_id=trace_id,
            span_id=span_id,
            extra={"query": query or {}},
        )
    except Exception:
        logger.exception("Failed to log audit log access.")
