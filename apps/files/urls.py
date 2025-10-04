from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.files.views import FileViewSet

router = DefaultRouter()

router.register(
    r"organizations/(?P<organization_uuid>[^/.]+)/files",
    FileViewSet,
    basename="file",
)

urlpatterns = [
    *router.urls,
]
