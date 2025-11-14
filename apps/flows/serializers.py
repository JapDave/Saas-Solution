from __future__ import annotations

from typing import Any, Dict

from rest_framework import serializers

from apps.flows.models import Flow, FlowVersion
from apps.flows.services import create_flow, save_draft_version


class FlowVersionSummarySerializer(serializers.ModelSerializer):
    created_by_email = serializers.EmailField(source="created_by.email", read_only=True)

    class Meta:
        model = FlowVersion
        fields = [
            "uuid",
            "version_number",
            "state",
            "is_active",
            "created_at",
            "created_by_email",
        ]


class FlowVersionDetailSerializer(FlowVersionSummarySerializer):
    flow_json = serializers.JSONField()
    flow_configurations = serializers.JSONField()
    description = serializers.CharField()
    name = serializers.CharField()

    class Meta(FlowVersionSummarySerializer.Meta):
        fields = FlowVersionSummarySerializer.Meta.fields + [
            "name",
            "description",
            "flow_configurations",
            "flow_json",
        ]


class FlowReadSerializer(serializers.ModelSerializer):
    organization_uuid = serializers.UUIDField(source="organization.uuid", read_only=True)
    active_versions = serializers.SerializerMethodField()
    state = serializers.SerializerMethodField()

    class Meta:
        model = Flow
        fields = [
            "uuid",
            "organization_uuid",
            "name",
            "description",
            "flow_configurations",
            "created_at",
            "updated_at",
            "deleted_at",
            "active_versions",
            "state",
        ]

    def get_active_versions(self, obj: Flow) -> Dict[str, Any]:
        versions = getattr(obj, "_prefetched_objects_cache", {}).get("versions") or obj.versions.all()
        active = [version for version in versions if version.is_active]
        serialized = {}
        for version in active:
            serialized[version.state] = FlowVersionSummarySerializer(version).data
        return serialized

    def get_state(self, obj: Flow) -> str | None:
        versions = getattr(obj, "_prefetched_objects_cache", {}).get("versions") or obj.versions.all()
        priorities = [
            FlowVersion.FlowVersionState.PUBLISHED,
            FlowVersion.FlowVersionState.DRAFT,
            FlowVersion.FlowVersionState.DISABLED,
        ]
        for state in priorities:
            if any(version for version in versions if version.is_active and version.state == state):
                return state
        return None


class FlowDetailSerializer(FlowReadSerializer):
    current_version = serializers.SerializerMethodField()

    class Meta(FlowReadSerializer.Meta):
        fields = FlowReadSerializer.Meta.fields + ["current_version"]

    def get_current_version(self, obj: Flow) -> Dict[str, Any] | None:
        versions = getattr(obj, "_prefetched_objects_cache", {}).get("versions") or obj.versions.all()
        active_versions = [version for version in versions if version.is_active]
        if not active_versions:
            return None
        latest = sorted(active_versions, key=lambda v: v.version_number)[-1]
        return FlowVersionDetailSerializer(latest).data


class FlowCreateSerializer(serializers.ModelSerializer):
    flow_json = serializers.JSONField()

    class Meta:
        model = Flow
        fields = ["name", "description", "flow_configurations", "flow_json"]

    def create(self, validated_data):
        organization = self.context["organization"]
        actor = self.context["request"].user
        flow_json = validated_data.pop("flow_json")
        return create_flow(
            organization=organization,
            actor=actor,
            flow_json=flow_json,
            **validated_data,
        )


class FlowUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Flow
        fields = ["name", "description", "flow_configurations"]

    def update(self, instance, validated_data):
        request = self.context.get("request")
        instance.updated_by = getattr(request, "user", None)
        return super().update(instance, validated_data)


class FlowVersionCreateSerializer(serializers.Serializer):
    flow_json = serializers.JSONField()
    flow_configurations = serializers.JSONField(required=False)
    name = serializers.CharField(required=False, allow_blank=False, max_length=250)
    description = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    previous_version_uuid = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, attrs):
        flow: Flow = self.context["flow"]
        if flow.versions.exists() and not attrs.get("previous_version_uuid"):
            raise serializers.ValidationError({"previous_version_uuid": "previousVersionId is required."})
        return attrs

    def create(self, validated_data):
        flow: Flow = self.context["flow"]
        actor = self.context["request"].user
        return save_draft_version(
            flow,
            actor=actor,
            flow_json=validated_data["flow_json"],
            flow_configurations=validated_data.get("flow_configurations"),
            name=validated_data.get("name"),
            description=validated_data.get("description"),
            previous_version_uuid=validated_data.get("previous_version_uuid"),
        )
