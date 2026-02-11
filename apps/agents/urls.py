from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.agents.views import (
    AgentViewSet,
<<<<<<< HEAD
    OrganizationLLMAvailableView,
    OrganizationLLMDisableView,
    OrganizationLLMView,
=======
    OrganizationToolAvailableView,
    OrganizationToolDisableView,
    OrganizationToolView,
>>>>>>> 6893b45f84d47c3ff959857580277f0cf6781e61
)

router = DefaultRouter()
router.register(r"agents", AgentViewSet, basename="agent")

urlpatterns = [
    path("", include(router.urls)),
    path(
<<<<<<< HEAD
        "organizations/<uuid:organization_uuid>/llms/",
        OrganizationLLMAvailableView.as_view(),
        name="organization-llms-available",
    ),
    path(
        "organizations/<uuid:organization_uuid>/llms/enabled/",
        OrganizationLLMView.as_view(),
        name="organization-llms",
    ),
    path(
        "organizations/<uuid:organization_uuid>/llms/<str:model_key>/disable/",
        OrganizationLLMDisableView.as_view(),
        name="organization-llms-disable",
=======
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
>>>>>>> 6893b45f84d47c3ff959857580277f0cf6781e61
    ),
]
