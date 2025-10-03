from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.roles.views import RoleViewSet, RoleAssignmentViewSet

router = DefaultRouter()

router.register(
    r"organizations/(?P<organization_uuid>[^/.]+)/roles",
    RoleViewSet,
    basename="role",
)

router.register(
    r"organizations/(?P<organization_uuid>[^/.]+)/role-assignments",
    RoleAssignmentViewSet,
    basename="role-assignment",
)

urlpatterns = [
    *router.urls,
]
