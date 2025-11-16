from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.knowledge_base.models import Collection, Resource


class CollectionReadSerializer(serializers.ModelSerializer):
    organization_uuid = serializers.UUIDField(source="organization.uuid", read_only=True)
    resource_count = serializers.IntegerField(source="resources.count", read_only=True)

    class Meta:
        model = Collection
        fields = [
            "uuid",
            "organization_uuid",
            "name",
            "description",
            "version",
            "state",
            "resource_count",
            "created_at",
            "updated_at",
        ]


class CollectionWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Collection
        fields = ["name", "description"]


class ResourceReadSerializer(serializers.ModelSerializer):
    file_id = serializers.UUIDField(source="file_uuid", read_only=True)
    file_name = serializers.CharField(source="file.name", read_only=True)

    class Meta:
        model = Resource
        fields = [
            "uuid",
            "file_id",
            "file_name",
            "file_type",
            "resource_type",
            "title",
            "summary",
            "is_broken_reference",
            "created_at",
            "updated_at",
        ]


class ResourceCreateSerializer(serializers.ModelSerializer):
    file_id = serializers.UUIDField(source="file_uuid")

    class Meta:
        model = Resource
        fields = ["file_id", "resource_type", "title", "summary"]


class ResourceMoveSerializer(serializers.Serializer):
    destination_collection_uuid = serializers.UUIDField()

