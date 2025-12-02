from rest_framework import serializers

from apps.files.models import File


class FileSerializer(serializers.ModelSerializer):
    organization_uuid = serializers.UUIDField(source="organization.uuid", read_only=True)
    parent_file_uuid = serializers.UUIDField(source="parent_file.uuid", read_only=True)

    class Meta:
        model = File
        fields = [
            "uuid",
            "organization_uuid",
            "name",
            "display_name",
            "description",
            "mime_type",
            "size",
            "hash",
            "file",
            "uploaded_by",
            "version",
            "parent_file_uuid",
            "is_public",
            "metadata",
            "tags",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "uuid",
            "hash",
            "organization_uuid",
            "uploaded_by",
            "version",
            "parent_file_uuid",
            "created_at",
            "updated_at",
        ]
