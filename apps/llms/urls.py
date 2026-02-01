from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.llms.views import (
    LLMValidationView,
    OrganizationLLMDisableView,
    OrganizationLLMEnableView,
    OrganizationLLMViewSet,
    OrganizationLLMDefinitionsView,
)

router = DefaultRouter()
router.register(
    r"llms/organizations/(?P<organization_uuid>[^/]+)/enabled",
    OrganizationLLMViewSet,
    basename="organization-llms",
)

urlpatterns = [
    # Available LLMs for an organization (filtered + usedByAgents)
    path(
        "llms/organizations/<uuid:organization_uuid>/",
        OrganizationLLMDefinitionsView.as_view(),
        name="organization-llms-available",
    ),
    path("llms/validate/", LLMValidationView.as_view(), name="llm-validate"),
    path(
        "llms/organizations/<uuid:organization_uuid>/<str:model_key>/enable/",
        OrganizationLLMEnableView.as_view(),
        name="organization-llms-enable",
    ),
    path(
        "llms/organizations/<uuid:organization_uuid>/<str:model_key>/disable/",
        OrganizationLLMDisableView.as_view(),
        name="organization-llms-disable",
    ),
    path("", include(router.urls)),
]
