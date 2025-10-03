from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.subscriptions.views import (
    SubscriptionViewSet,
)
router = DefaultRouter()
router.register(
    r"organizations/(?P<organization_uuid>[^/.]+)/subscriptions",
    SubscriptionViewSet,
    basename="subscription"
)

urlpatterns = [
    *router.urls,
]
