from django.urls import path

from rest_framework.routers import DefaultRouter

from .views import TeamViewSet

router = DefaultRouter()
router.register(r"teams", TeamViewSet, basename="team")

urlpatterns = [
    *router.urls,
]

__all__ = ["urlpatterns"]
