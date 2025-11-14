from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.flows.views import FlowVersionViewSet, FlowViewSet

router = DefaultRouter()
router.register(
    r"organizations/(?P<organization_uuid>[^/]+)/flows",
    FlowViewSet,
    basename="organization-flows",
)
router.register(
    r"organizations/(?P<organization_uuid>[^/]+)/flows/(?P<flow_uuid>[^/]+)/versions",
    FlowVersionViewSet,
    basename="flow-versions",
)

urlpatterns = [
    path("", include(router.urls)),
]

