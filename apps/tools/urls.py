from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.tools.views import (
    OrganizationToolDisableView,
    OrganizationToolEnableView,
    OrganizationToolViewSet,
    ToolDefinitionDetailView,
    ToolDefinitionListView,
    ToolSchemaView,
    ToolValidationView,
)

router = DefaultRouter()
router.register(
    r"tools/organizations/(?P<organization_uuid>[^/]+)/enabled",
    OrganizationToolViewSet,
    basename="organization-tools",
)

urlpatterns = [
    path("tools/", ToolDefinitionListView.as_view(), name="tool-list"),
    path("tools/validate/", ToolValidationView.as_view(), name="tool-validate"),
    path("tools/<str:tool_key>/schema/", ToolSchemaView.as_view(), name="tool-schema"),
    path("tools/<str:tool_key>/", ToolDefinitionDetailView.as_view(), name="tool-detail"),
    path(
        "tools/organizations/<uuid:organization_uuid>/<str:tool_key>/enable/",
        OrganizationToolEnableView.as_view(),
        name="organization-tools-enable",
    ),
    path(
        "tools/organizations/<uuid:organization_uuid>/<str:tool_key>/disable/",
        OrganizationToolDisableView.as_view(),
        name="organization-tools-disable",
    ),
    path("", include(router.urls)),
]
