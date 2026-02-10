from __future__ import annotations

from rest_framework import serializers

class ToolDefinitionSerializer(serializers.Serializer):
    toolKey = serializers.CharField()
    displayName = serializers.CharField()
    description = serializers.CharField()
    category = serializers.CharField()
    configurationSchema = serializers.DictField()
    usedByAgents = serializers.IntegerField(required=False)


class OrganizationEnabledToolSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="uuid")
    organizationId = serializers.UUIDField(source="organization.uuid")
    toolKey = serializers.CharField(source="tool_key")
    displayName = serializers.CharField(source="display_name")
    category = serializers.CharField()
    enabledBy = serializers.UUIDField(source="enabled_by.uuid", allow_null=True)
    enabledAt = serializers.DateTimeField(source="enabled_at")
    disabledAt = serializers.DateTimeField(source="disabled_at", allow_null=True)
    disabledBy = serializers.UUIDField(source="disabled_by.uuid", allow_null=True)
