from __future__ import annotations

from rest_framework import serializers

from apps.agents.models import OrganizationEnabledTool


class ToolDefinitionSerializer(serializers.Serializer):
    toolKey = serializers.CharField()
    displayName = serializers.CharField()
    description = serializers.CharField()
    categories = serializers.ListField(child=serializers.CharField(), required=False)


class ToolValidationSerializer(serializers.Serializer):
    organization_uuid = serializers.UUIDField()
    toolKey = serializers.CharField()
    configuration = serializers.DictField()


class OrganizationEnabledToolSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganizationEnabledTool
        fields = ["uuid", "tool_key", "enabled_at", "disabled_at"]

