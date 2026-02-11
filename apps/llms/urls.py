from django.urls import path

from apps.llms.views import (
    LLMValidationView,
    OrganizationLLMDisableView,
    OrganizationLLMEnableView,
    OrganizationLLMDefinitionsView,
    OrganizationLLMEnabledView,
)

urlpatterns = [
    # Available LLMs for an organization (filtered + usedByAgents)
    path(
        "llms/organizations/<uuid:organization_uuid>/",
        OrganizationLLMDefinitionsView.as_view(),
        name="organization-llms-available",
    ),
    path(
        "llms/organizations/<uuid:organization_uuid>/enabled/",
        OrganizationLLMEnabledView.as_view(),
        name="organization-llms-list",
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
]
