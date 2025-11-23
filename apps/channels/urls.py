from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.channels.views import (
    ChannelAccessGrantViewSet,
    ChannelTypeEnabledView,
    ChannelTypeListView,
    ChannelViewSet,
)

router = DefaultRouter()
router.register(
    r"organizations/(?P<organization_uuid>[^/]+)/channels",
    ChannelViewSet,
    basename="organization-channels",
)
router.register(
    r"organizations/(?P<organization_uuid>[^/]+)/channels/(?P<channel_uuid>[^/]+)/grants",
    ChannelAccessGrantViewSet,
    basename="channel-grants",
)

urlpatterns = [
    path("", include(router.urls)),
    path(
        "organizations/<uuid:organization_uuid>/channel-types/",
        ChannelTypeListView.as_view(),
        name="channel-types",
    ),
    path(
        "organizations/<uuid:organization_uuid>/channel-types/enabled/",
        ChannelTypeEnabledView.as_view(),
        name="channel-types-enabled",
    ),
]
