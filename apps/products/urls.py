from django.urls import path

from rest_framework.routers import DefaultRouter


from apps.products.views import (
    ProductViewSet,
    ModuleViewSet,
)

router = DefaultRouter()
router.register(r"products", ProductViewSet, basename="product")
router.register(r"modules", ModuleViewSet, basename="module")

urlpatterns = [
    *router.urls,
]
