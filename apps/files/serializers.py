from rest_framework import serializers

from apps.files.models import File

class FileSerializer(serializers.ModelSerializer):
    class Meta:
        model = File
        fields = [
            "id",
            "uuid",
            "name",
            "display_name",
            "description",
            "mime_type",
            "size",
            "hash",
            "file",
            "organization",
            "uploaded_by",
            "version",
            "parent_file",
            "is_public",
            "metadata",
            "tags",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "uuid",
            "hash",
            "parent_file",
            "organization",
            "uploaded_by",
        ]
