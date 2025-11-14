from __future__ import annotations

from typing import Any, Dict

from rest_framework import serializers

from apps.integrations.models import Integration
from apps.integrations.services import enforce_integration_limit, resolve_integration_limits


class IntegrationReadSerializer(serializers.ModelSerializer):
    organization_uuid = serializers.UUIDField(source="organization.uuid", read_only=True)
    webhook_secret = serializers.SerializerMethodField()

    class Meta:
        model = Integration
        fields = [
            "uuid",
            "organization_uuid",
            "integration_type",
            "name",
            "description",
            "state",
            "is_active",
            "url",
            "method",
            "headers",
            "parameters",
            "request_body",
            "response_mappings",
            "webhook_url",
            "webhook_sample_payload",
            "invocation_count_month",
            "invocation_count_total",
            "invocation_month",
            "last_invocation_at",
            "created_at",
            "updated_at",
            "webhook_secret",
        ]

    def get_webhook_secret(self, obj: Integration):
        include = self.context.get("include_secret", False)
        if include and obj.integration_type == Integration.IntegrationType.WEBHOOK:
            return obj.webhook_secret
        return None


class IntegrationWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Integration
        fields = [
            "integration_type",
            "name",
            "description",
            "url",
            "method",
            "headers",
            "parameters",
            "request_body",
            "response_mappings",
            "webhook_sample_payload",
        ]

    def _organization(self):
        organization = self.context.get("organization")
        if not organization:
            raise serializers.ValidationError({"organization": "organization context is required."})
        return organization

    def validate(self, attrs):
        integration_type = attrs.get("integration_type") or getattr(self.instance, "integration_type", None)
        if integration_type not in Integration.IntegrationType.values:
            raise serializers.ValidationError({"integration_type": "Invalid integration type."})

        if integration_type == Integration.IntegrationType.API:
            missing_fields = ["url", "method", "response_mappings"]
            for field in missing_fields:
                attrs.setdefault(field, attrs.get(field) or getattr(self.instance, field, ""))
        elif integration_type == Integration.IntegrationType.WEBHOOK:
            attrs.setdefault("response_mappings", attrs.get("response_mappings") or getattr(self.instance, "response_mappings", []))
            attrs.setdefault(
                "webhook_sample_payload",
                attrs.get("webhook_sample_payload") or getattr(self.instance, "webhook_sample_payload", {}),
            )
        else:
            raise serializers.ValidationError({"integration_type": "Unsupported integration type."})
        attrs["integration_type"] = integration_type
        return attrs

    def create(self, validated_data):
        organization = self._organization()
        request = self.context.get("request")
        user = getattr(request, "user", None)
        integration_type = validated_data["integration_type"]
        enforce_integration_limit(organization, integration_type)
        integration = Integration(
            organization=organization,
            integration_type=integration_type,
            name=validated_data["name"],
            description=validated_data.get("description", ""),
            created_by=user,
            updated_by=user,
        )
        integration.url = validated_data.get("url", "")
        integration.method = validated_data.get("method", "")
        integration.headers = validated_data.get("headers", [])
        integration.parameters = validated_data.get("parameters", [])
        integration.request_body = validated_data.get("request_body", "")
        integration.response_mappings = validated_data.get("response_mappings", [])
        integration.webhook_sample_payload = validated_data.get("webhook_sample_payload", {})
        if integration.integration_type == Integration.IntegrationType.WEBHOOK:
            integration.regenerate_webhook_credentials()
        integration.full_clean()
        integration.save()
        return integration

    def update(self, instance, validated_data):
        for attr in ["name", "description", "url", "method", "headers", "parameters", "request_body", "response_mappings", "webhook_sample_payload"]:
            if attr in validated_data:
                setattr(instance, attr, validated_data[attr])
        instance.updated_by = getattr(self.context.get("request"), "user", None)
        instance.full_clean()
        instance.save()
        return instance


class IntegrationTestSerializer(serializers.Serializer):
    parameters = serializers.DictField(child=serializers.CharField(), required=False)


class IntegrationAnalyticsSerializer(serializers.Serializer):
    integration_type = serializers.CharField()
    active = serializers.IntegerField()
    inactive = serializers.IntegerField()
    deleted = serializers.IntegerField()
    invocation_count_month = serializers.IntegerField()
    invocation_count_total = serializers.IntegerField()


class IntegrationTypeSerializer(serializers.Serializer):
    integration_type = serializers.CharField()
    enabled = serializers.BooleanField()
    max_instances = serializers.IntegerField()
    max_invocations = serializers.IntegerField()


def integration_type_payload(organization) -> list[dict[str, Any]]:
    limits = resolve_integration_limits(organization)
    payload = []
    for key, meta in limits.items():
        payload.append(
            {
                "integrationType": key,
                "enabled": meta.enabled,
                "maxInstances": meta.max_instances,
                "maxInvocationsPerMonth": meta.max_invocations,
            }
        )
    return payload
