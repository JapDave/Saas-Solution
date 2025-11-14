from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import serializers

from apps.channels.models import Channel, ChannelAccessGrant
from apps.channels.validators import validate_channel_configuration
from apps.channels.definitions import CHANNEL_TYPE_CHOICES, CHANNEL_INSTANCE_PERMISSION_KEYS
from apps.organizations.models import Organization
from apps.teams.models import Team
from apps.users.models import User


class ChannelReadSerializer(serializers.ModelSerializer):
    channel_type_id = serializers.CharField(source="channel_type", read_only=True)
    organization_uuid = serializers.UUIDField(source="organization.uuid", read_only=True)
    created_by_email = serializers.EmailField(source="created_by.email", read_only=True)

    class Meta:
        model = Channel
        fields = [
            "uuid",
            "organization_uuid",
            "channel_type_id",
            "name",
            "description",
            "state",
            "configurations",
            "created_by_email",
            "created_at",
            "updated_at",
        ]


class ChannelWriteSerializer(serializers.ModelSerializer):
    channel_type = serializers.ChoiceField(choices=CHANNEL_TYPE_CHOICES)

    class Meta:
        model = Channel
        fields = [
            "channel_type",
            "name",
            "description",
            "configurations",
        ]

    def validate_channel_type(self, value):
        if self.instance and value != self.instance.channel_type:
            raise serializers.ValidationError("Channel type cannot be changed.")
        return value

    def validate_configurations(self, value):
        channel_type = self.initial_data.get("channel_type") or getattr(self.instance, "channel_type", None)
        if not channel_type:
            raise serializers.ValidationError("channel_type is required before validating configuration.")
        return validate_channel_configuration(channel_type, value or {})


class ChannelAccessGrantSerializer(serializers.ModelSerializer):
    subject_user_email = serializers.EmailField(source="subject_user.email", read_only=True)
    subject_team_name = serializers.CharField(source="subject_team.name", read_only=True)

    class Meta:
        model = ChannelAccessGrant
        fields = [
            "uuid",
            "subject_type",
            "subject_user_email",
            "subject_team_name",
            "permissions",
            "granted_at",
            "revoked_at",
        ]


class ChannelAccessGrantCreateSerializer(serializers.Serializer):
    subject_type = serializers.ChoiceField(choices=ChannelAccessGrant.SubjectType.choices)
    subject_id = serializers.UUIDField()
    permissions = serializers.ListField(
        child=serializers.ChoiceField(choices=[(perm, perm) for perm in CHANNEL_INSTANCE_PERMISSION_KEYS]),
        min_length=1,
    )

    def validate(self, attrs):
        channel: Channel = self.context["channel"]
        organization = channel.organization
        subject_type = attrs["subject_type"]
        subject_id = attrs["subject_id"]
        if subject_type == ChannelAccessGrant.SubjectType.USER:
            user = get_object_or_404(User, uuid=subject_id)
            if not user.memberships.filter(organization=organization, deleted_at__isnull=True).exists():
                raise serializers.ValidationError({"subject_id": "User is not part of the organization."})
            attrs["subject_user"] = user
        else:
            team = get_object_or_404(Team, uuid=subject_id, organization=organization)
            attrs["subject_team"] = team
        attrs["organization"] = organization
        attrs["channel"] = channel
        return attrs
