from rest_framework import serializers

from .models import Product, Module


class ModuleSerializer(serializers.ModelSerializer):
    """Serializer for the Module model."""

    class Meta:
        model = Module
        fields = [
            "id",
            "key",
            "code",
            "name",
            "description",
            "subscribable",
            "configurable_attributes",
            "exposed_permissions",
            "is_active",
            "created_at",
            "updated_at",
        ]


class ProductSerializer(serializers.ModelSerializer):
    """Serializer for the Product model."""

    class Meta:
        model = Product
        fields = [
            "id",
            "key",
            "name",
            "description",
            "available_module_keys",
            "target_segments",
            "use_cases",
            "is_active",
            "created_at",
            "updated_at",
        ]
