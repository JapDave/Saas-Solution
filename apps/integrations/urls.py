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
    r"integrations/organizations/(?P<organization_uuid>[^/]+)",
    IntegrationViewSet,
    basename="organization-integrations",
)

urlpatterns = [
    path(
        "integrations/organizations/<uuid:organization_uuid>/analytics/",
        IntegrationAnalyticsView.as_view(),
        name="integration-analytics",
    ),
    path(
        "integrations/organizations/<uuid:organization_uuid>/<uuid:integration_uuid>/analytics/",
        IntegrationAnalyticsDetailView.as_view(),
        name="integration-analytics-detail",
    ),
    path(
        "integrations/organizations/<uuid:organization_uuid>/types/",
        IntegrationTypesView.as_view(),
        name="integration-types",
    ),
    path("", include(router.urls)),
]
