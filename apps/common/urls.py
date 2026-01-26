from __future__ import annotations

from rest_framework.routers import DefaultRouter

from apps.common.views import AuditLogViewSet

router = DefaultRouter()
router.register("audit-logs", AuditLogViewSet, basename="audit-log")

urlpatterns = router.urls
