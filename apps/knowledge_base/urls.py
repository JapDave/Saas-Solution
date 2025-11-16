from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.knowledge_base.views import CollectionViewSet, ResourceViewSet

router = DefaultRouter()
router.register(
    r"knowledge-base/organizations/(?P<organization_uuid>[^/]+)/collections",
    CollectionViewSet,
    basename="kb-collections",
)
router.register(
    r"knowledge-base/organizations/(?P<organization_uuid>[^/]+)/collections/(?P<collection_uuid>[^/]+)/resources",
    ResourceViewSet,
    basename="kb-resources",
)

urlpatterns = [
    path("", include(router.urls)),
]
