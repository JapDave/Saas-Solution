from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers


class LLMDefinitionSerializer(serializers.Serializer):
    modelKey = serializers.CharField()
    modelProvider = serializers.CharField()
    displayName = serializers.CharField()
    description = serializers.CharField()
    maxContextTokens = serializers.IntegerField(required=False)
    supportedModalities = serializers.ListField(child=serializers.CharField(), required=False)
    modelConfiguration = serializers.DictField(required=False)
    usedByAgents = serializers.IntegerField(required=False)
    disabledAt = serializers.DateTimeField(required=False)
    warning = serializers.CharField(required=False, allow_blank=True)


class LLMEnableSerializer(serializers.Serializer):
    model_key = serializers.CharField()


class LLMValidationSerializer(serializers.Serializer):
    organization_uuid = serializers.UUIDField()
    modelKey = serializers.CharField()
    modelProvider = serializers.CharField(required=False, allow_blank=True)
    configuration = serializers.DictField()
