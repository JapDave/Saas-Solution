from __future__ import annotations

from typing import Any

from django.shortcuts import get_object_or_404
from rest_framework import serializers

from apps.agents.models import (
    Agent,
    AgentVersion,
    OrganizationEnabledLLM,
    OrganizationEnabledTool,
)
from apps.agents.services import save_agent_version
from apps.agents.validators import (
    validate_llm_configuration,
    validate_system_prompts,
    validate_tools_configuration,
)
from apps.organizations.models import Organization


class OrganizationSlugRelatedField(serializers.SlugRelatedField):
    def to_internal_value(self, data):
        try:
            return super().to_internal_value(data)
        except serializers.ValidationError as exc:
            raise serializers.ValidationError({"organization": exc.detail})


class AgentReadSerializer(serializers.ModelSerializer):
    organization_uuid = serializers.UUIDField(source="organization.uuid", read_only=True)
    current_version_uuid = serializers.UUIDField(source="current_version.uuid", read_only=True)
    current_version_number = serializers.IntegerField(source="current_version.version_number", read_only=True)

    class Meta:
        model = Agent
        fields = [
            "uuid",
            "organization_uuid",
            "name",
            "description",
            "system_prompts",
            "llm_configuration",
            "tools_configuration",
            "state",
            "current_version_uuid",
            "current_version_number",
            "created_at",
            "updated_at",
        ]


class AgentWriteSerializer(serializers.ModelSerializer):
    organization = OrganizationSlugRelatedField(
        slug_field="uuid",
        queryset=Organization.objects.all(),
        required=True,
    )

    class Meta:
        model = Agent
        fields = [
            "organization",
            "name",
            "description",
            "system_prompts",
            "llm_configuration",
            "tools_configuration",
            "state",
        ]
        read_only_fields = ["state"]

    def _organization(self, attrs):
        organization = attrs.get("organization") or getattr(self.instance, "organization", None)
        if not organization:
            raise serializers.ValidationError({"organization": "organization is required."})
        return organization

    def validate(self, attrs):
        organization = self._organization(attrs)

        if "system_prompts" in attrs or not self.instance:
            system_prompts = attrs.get("system_prompts") or getattr(self.instance, "system_prompts", "")
            if not system_prompts:
                raise serializers.ValidationError({"system_prompts": "systemPrompts is required."})
            validate_system_prompts(system_prompts)

        if "llm_configuration" in attrs or not self.instance:
            llm_config = attrs.get("llm_configuration") or getattr(self.instance, "llm_configuration", {})
            attrs["llm_configuration"] = validate_llm_configuration(llm_config, organization=organization)

        if "tools_configuration" in attrs or not self.instance:
            tools_config = attrs.get("tools_configuration") or getattr(self.instance, "tools_configuration", [])
            attrs["tools_configuration"] = validate_tools_configuration(tools_config, organization=organization)

        name = attrs.get("name")
        if name:
            attrs["name"] = name.strip()
        description = attrs.get("description")
        if description is not None:
            attrs["description"] = description.strip()
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        validated_data["created_by"] = user
        validated_data["updated_by"] = user
        agent = super().create(validated_data)
        if user:
            save_agent_version(agent, actor=user)
        return agent

    def update(self, instance, validated_data):
        validated_data["updated_by"] = getattr(self.context.get("request"), "user", None)
        return super().update(instance, validated_data)


class AgentVersionSerializer(serializers.ModelSerializer):
    agent_uuid = serializers.UUIDField(source="agent.uuid", read_only=True)
    created_by_email = serializers.EmailField(source="created_by.email", read_only=True)

    class Meta:
        model = AgentVersion
        fields = [
            "uuid",
            "agent_uuid",
            "version_number",
            "name",
            "description",
            "system_prompts",
            "llm_configuration",
            "tools_configuration",
            "created_by_email",
            "created_at",
        ]


class AgentVersionCreateSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, allow_blank=False, max_length=250)
    description = serializers.CharField(required=False, allow_blank=True, max_length=250)
    system_prompts = serializers.CharField(required=False)
    llm_configuration = serializers.JSONField(required=False)
    tools_configuration = serializers.JSONField(required=False)

    def validate(self, attrs):
        agent: Agent = self.context["agent"]

        if "name" in attrs:
            attrs["name"] = attrs["name"].strip()

        if "system_prompts" in attrs:
            validate_system_prompts(attrs["system_prompts"])

        if "llm_configuration" in attrs:
            attrs["llm_configuration"] = validate_llm_configuration(
                attrs["llm_configuration"], organization=agent.organization
            )

        if "tools_configuration" in attrs:
            attrs["tools_configuration"] = validate_tools_configuration(
                attrs["tools_configuration"], organization=agent.organization
            )
        return attrs


class VersionSwitchSerializer(serializers.Serializer):
    version_uuid = serializers.UUIDField()


class CloneAgentSerializer(serializers.Serializer):
    organization_uuid = serializers.UUIDField(required=False)


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
