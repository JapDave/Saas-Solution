from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.integrations.views import (
    IntegrationAnalyticsDetailView,
    IntegrationAnalyticsView,
    IntegrationTypesView,
    IntegrationViewSet,
)

router = DefaultRouter()
router.register(
    r"organizations/(?P<organization_uuid>[^/]+)/integrations",
    IntegrationViewSet,
    basename="organization-integrations",
)

urlpatterns = [
    path(
        "organizations/<uuid:organization_uuid>/integrations/analytics/",
        IntegrationAnalyticsView.as_view(),
        name="integration-analytics",
    ),
    path(
        "organizations/<uuid:organization_uuid>/integrations/<uuid:integration_uuid>/analytics/",
        IntegrationAnalyticsDetailView.as_view(),
        name="integration-analytics-detail",
    ),
    path(
        "organizations/<uuid:organization_uuid>/integration-types/",
        IntegrationTypesView.as_view(),
        name="integration-types",
    ),
    path("", include(router.urls)),
]
