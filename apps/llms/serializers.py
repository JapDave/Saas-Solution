from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.agents.models import OrganizationEnabledLLM
from apps.agents.definitions import get_llm_definition


class LLMDefinitionSerializer(serializers.Serializer):
    modelKey = serializers.CharField()
    modelProvider = serializers.CharField()
    displayName = serializers.CharField()
    description = serializers.CharField()
    maxContextTokens = serializers.IntegerField(required=False)
    supportedModalities = serializers.ListField(child=serializers.CharField(), required=False)


class LLMEnableSerializer(serializers.Serializer):
    model_key = serializers.CharField()


class LLMValidationSerializer(serializers.Serializer):
    organization_uuid = serializers.UUIDField()
    modelKey = serializers.CharField()
    modelProvider = serializers.CharField(required=False, allow_blank=True)
    configuration = serializers.DictField(required=False)


class OrganizationEnabledLLMSerializer(serializers.ModelSerializer):
    model_key = serializers.CharField()
    model_provider = serializers.CharField()

    class Meta:
        model = OrganizationEnabledLLM
        fields = ["uuid", "model_key", "model_provider", "enabled_at", "disabled_at"]

