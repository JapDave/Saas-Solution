from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.llms.views import (
    LLMDefinitionDetailView,
    LLMDefinitionListView,
    LLMDefinitionSchemaView,
    LLMValidationView,
    OrganizationLLMDisableView,
    OrganizationLLMEnableView,
    OrganizationLLMViewSet,
)

router = DefaultRouter()
router.register(
    r"llms/organizations/(?P<organization_uuid>[^/]+)/enabled",
    OrganizationLLMViewSet,
    basename="organization-llms",
)

urlpatterns = [
    path("llms/", LLMDefinitionListView.as_view(), name="llm-list"),
    path("llms/validate/", LLMValidationView.as_view(), name="llm-validate"),
    path("llms/<str:model_key>/schema/", LLMDefinitionSchemaView.as_view(), name="llm-schema"),
    path("llms/<str:model_key>/", LLMDefinitionDetailView.as_view(), name="llm-detail"),
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
