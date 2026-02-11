from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.agents.views import (
    AgentViewSet,
    OrganizationToolAvailableView,
    OrganizationToolDisableView,
    OrganizationToolView,
)

router = DefaultRouter()
router.register(r"agents", AgentViewSet, basename="agent")

urlpatterns = [
    path("", include(router.urls)),
    path(
        "organizations/<uuid:organization_uuid>/tools/",
        OrganizationToolAvailableView.as_view(),
        name="organization-tools-available",
    ),
    path(
        "organizations/<uuid:organization_uuid>/tools/enabled/",
        OrganizationToolView.as_view(),
        name="organization-tools",
    ),
    path(
        "organizations/<uuid:organization_uuid>/tools/<str:tool_key>/disable/",
        OrganizationToolDisableView.as_view(),
        name="organization-tools-disable",
    ),
]
