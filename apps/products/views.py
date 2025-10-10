# Django/DRF imports
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

# 3rd party imports
from django_filters.rest_framework import DjangoFilterBackend

# Project imports
from apps.products.models import (
    Product,
    Module,
)
from apps.products.serializers import (
    ProductSerializer,
    ModuleSerializer,
)


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """
    A read-only viewset for viewing active products.
    Provides `list` and `retrieve` actions.
    """
    queryset = Product.objects.filter(is_active=True)
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated, ]
    lookup_field = "uuid"
    ERROR_DOMAIN = "products"


class ModuleViewSet(viewsets.ReadOnlyModelViewSet):
    """
    A read-only viewset for viewing active modules.
    Provides `list` and `retrieve` actions.
    """
    queryset = Module.objects.filter(is_active=True)
    serializer_class = ModuleSerializer
    permission_classes = [IsAuthenticated, ]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["products",]
    ordering_fields = ["created_at", "key", "code", "name", "-name"]
    lookup_field = "uuid"
    ERROR_DOMAIN = "modules"

    @action(detail=True, methods=["get"], url_path="config-schema", url_name="config-schema")
    def config_schema(self, request, pk=None, *args, **kwargs):
        """
        Retrieve the configuration schema for a module.
        """
        module = self.get_object()
        return Response(
            data=module.configurable_attributes,
            status=status.HTTP_200_OK
        )


