from django.urls import path

from apps.tools.views import (
    OrganizationToolDetailView,
    OrganizationToolDisableView,
    OrganizationToolEnableView,
    OrganizationToolEnabledListView,
    OrganizationToolListView,
)

urlpatterns = [
    path("tools/organizations/<uuid:organization_uuid>/", OrganizationToolListView.as_view(), name="tool-list"),
    path(
        "tools/organizations/<uuid:organization_uuid>/enabled/",
        OrganizationToolEnabledListView.as_view(),
        name="tool-enabled-list",
    ),
    path(
        "tools/organizations/<uuid:organization_uuid>/<str:tool_key>/",
        OrganizationToolDetailView.as_view(),
        name="tool-detail",
    ),
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
]
