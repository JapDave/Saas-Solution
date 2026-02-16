from __future__ import annotations

from rest_framework import serializers

from apps.agents.models import Agent, AgentVersion, OrganizationEnabledLLM, OrganizationEnabledTool
from apps.agents.validators import (
    validate_agent_description,
    validate_agent_name,
    validate_system_prompts,
)


class AgentReadSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="uuid", read_only=True)
    organizationId = serializers.UUIDField(source="organization.uuid", read_only=True)
    currentVersionId = serializers.UUIDField(source="current_version.uuid", read_only=True, allow_null=True)
    createdBy = serializers.UUIDField(source="created_by.uuid", read_only=True, allow_null=True)
    updatedBy = serializers.UUIDField(source="updated_by.uuid", read_only=True, allow_null=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)
    deletedAt = serializers.DateTimeField(source="deleted_at", read_only=True, allow_null=True)

    class Meta:
        model = Agent
        fields = [
            "id",
            "organizationId",
            "name",
            "description",
            "currentVersionId",
            "state",
            "createdBy",
            "updatedBy",
            "createdAt",
            "updatedAt",
            "deletedAt",
        ]


class AgentCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=250)
    description = serializers.CharField(required=False, allow_blank=True, max_length=250)

    def validate_name(self, value):
        return validate_agent_name(value)

    def validate_description(self, value):
        return validate_agent_description(value)


class AgentPatchSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, allow_blank=False, max_length=250)
    description = serializers.CharField(required=False, allow_blank=True, max_length=250)
    currentVersionId = serializers.UUIDField(required=False, source="current_version_id")
    state = serializers.ChoiceField(required=False, choices=Agent.AgentState.choices)

    def validate_name(self, value):
        return validate_agent_name(value)

    def validate_description(self, value):
        return validate_agent_description(value)


class AgentVersionSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="uuid", read_only=True)
    agentId = serializers.UUIDField(source="agent.uuid", read_only=True)
    versionNumber = serializers.IntegerField(source="version_number", read_only=True)
    systemPrompts = serializers.JSONField(source="system_prompts", read_only=True)
    llmConfiguration = serializers.JSONField(source="llm_configuration", read_only=True)
    toolsConfiguration = serializers.JSONField(source="tools_configuration", read_only=True)
    createdBy = serializers.UUIDField(source="created_by.uuid", read_only=True, allow_null=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = AgentVersion
        fields = [
            "id",
            "agentId",
            "versionNumber",
            "name",
            "description",
            "systemPrompts",
            "llmConfiguration",
            "toolsConfiguration",
            "createdBy",
            "createdAt",
        ]


class AgentVersionCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=250, required=False, allow_blank=False)
    description = serializers.CharField(required=False, allow_blank=True, max_length=250)
    systemPrompts = serializers.JSONField(source="system_prompts")
    llmConfiguration = serializers.JSONField(source="llm_configuration")
    toolsConfiguration = serializers.JSONField(required=False, source="tools_configuration")

    def validate_name(self, value):
        return validate_agent_name(value)

    def validate_description(self, value):
        return validate_agent_description(value)

    def validate_systemPrompts(self, value):
        return validate_system_prompts(value)


class LLMEnableSerializer(serializers.Serializer):
    model_key = serializers.CharField()


class ToolEnableSerializer(serializers.Serializer):
    tool_key = serializers.CharField()


class OrganizationEnabledLLMSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganizationEnabledLLM
        fields = ["model_key", "model_provider", "enabled_at", "disabled_at", "uuid"]


class OrganizationEnabledToolSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganizationEnabledTool
        fields = ["tool_key", "enabled_at", "disabled_at", "uuid"]
