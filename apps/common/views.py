from __future__ import annotations

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.common.audit import log_audit_access
from apps.common.models import AuditLog
from apps.common.serializers import AuditLogSerializer
from apps.roles.permissions import IsSaaSAdmin


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only audit log access for authorized operators."""

    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated, IsSaaSAdmin]
    queryset = AuditLog.objects.all().order_by("-created_at")
    filterset_fields = {
        "user": ["exact"],
        "app_label": ["exact"],
        "model": ["exact"],
        "action": ["exact"],
        "trace_id": ["exact"],
        "success": ["exact"],
        "status_code": ["exact"],
        "created_at": ["gte", "lte"],
    }

    def list(self, request, *args, **kwargs):
        try:
            response = super().list(request, *args, **kwargs)
        except Exception:
            log_audit_access(
                request,
                action="query",
                query=request.query_params,
                success=False,
            )
            raise
        log_audit_access(
            request,
            action="query",
            query=request.query_params,
            success=True,
        )
        return response

    def retrieve(self, request, *args, **kwargs):
        try:
            response = super().retrieve(request, *args, **kwargs)
        except Exception:
            log_audit_access(
                request,
                action="read",
                query={"id": kwargs.get("pk")},
                success=False,
            )
            raise
        log_audit_access(
            request,
            action="read",
            query={"id": kwargs.get("pk")},
            success=True,
        )
        return response

    def permission_denied(self, request, message=None, code=None):
        log_audit_access(
            request,
            action="access_denied",
            query=dict(request.query_params),
            success=False,
        )
        return super().permission_denied(request, message=message, code=code)
