from __future__ import annotations

import logging

from apps.common.audit import get_audit_context, get_trace_context


class APMTraceFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        trace_id, span_id = get_trace_context()
        context = get_audit_context()
        request = context.request
        user = context.user

        record.trace_id = trace_id or ""
        record.span_id = span_id or ""
        record.request_id = getattr(record, "request_id", None) or (
            request.META.get("HTTP_X_REQUEST_ID") if request else ""
        )
        record.user = getattr(user, "id", None) or ""
        record.org = ""
        if request and hasattr(request, "session"):
            record.org = request.session.get("active_organization_id", "") or ""
        return True
