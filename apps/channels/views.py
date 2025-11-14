from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.channels.definitions import CHANNEL_CONFIGURATION_SCHEMAS, CHANNEL_TYPE_CHOICES
from apps.channels.models import Channel, ChannelAccessGrant
from apps.channels.serializers import (
    ChannelAccessGrantCreateSerializer,
    ChannelAccessGrantSerializer,
    ChannelReadSerializer,
    ChannelWriteSerializer,
)
from apps.channels.services import (
    ensure_channel_acl,
    ensure_org_channel_permission,
    enforce_channel_instance_limit,
    ensure_channel_type_enabled,
    resolve_channel_limits,
    revoke_channel_grants,
)
from apps.common.exceptions import CustomError, INVALID_STATE_TRANSITION
from apps.organizations.models import Organization


class ChannelViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    lookup_field = "uuid"

    def _organization(self):
        return get_object_or_404(Organization, uuid=self.kwargs["organization_uuid"])

    def get_queryset(self):
        organization = self._organization()
        qs = Channel.objects.filter(organization=organization).select_related("organization", "created_by", "updated_by")
        return qs

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return ChannelWriteSerializer
        return ChannelReadSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["organization"] = self._organization()
        return context

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        channel = self._save_channel(serializer, request.user)
        read = ChannelReadSerializer(channel, context=self.get_serializer_context())
        headers = self.get_success_headers(read.data)
        return Response(read.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        ensure_org_channel_permission(request.user, instance.organization, "channels:update")
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        channel = serializer.save(updated_by=request.user)
        read = ChannelReadSerializer(channel, context=self.get_serializer_context())
        return Response(read.data)

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def _save_channel(self, serializer, user):
        organization = self._organization()
        ensure_org_channel_permission(user, organization, "channels:create")
        channel_type = serializer.validated_data["channel_type"]
        ensure_channel_type_enabled(organization, channel_type)
        enforce_channel_instance_limit(organization, channel_type)
        return serializer.save(
            organization=organization,
            created_by=user,
            updated_by=user,
        )

    def perform_destroy(self, instance):
        ensure_org_channel_permission(self.request.user, instance.organization, "channels:delete")
        instance.mark_deleted()
        revoke_channel_grants(instance)

    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, organization_uuid=None, uuid=None):
        channel = self.get_object()
        ensure_org_channel_permission(request.user, channel.organization, "channels:activate")
        if channel.state == Channel.ChannelState.DELETED:
            raise CustomError(code="CHANNEL_DELETED", status_code=400, detail="Channel is deleted.")
        channel.state = Channel.ChannelState.ACTIVE
        channel.save(update_fields=["state", "updated_at"])
        return Response(ChannelReadSerializer(channel).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="deactivate")
    def deactivate(self, request, organization_uuid=None, uuid=None):
        channel = self.get_object()
        ensure_org_channel_permission(request.user, channel.organization, "channels:activate")
        if channel.state == Channel.ChannelState.DELETED:
            raise CustomError(code="CHANNEL_DELETED", status_code=400, detail="Channel is deleted.")
        channel.state = Channel.ChannelState.INACTIVE
        channel.save(update_fields=["state", "updated_at"])
        return Response(ChannelReadSerializer(channel).data, status=status.HTTP_200_OK)


class ChannelAccessGrantViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    lookup_field = "uuid"

    def _channel(self):
        organization = get_object_or_404(Organization, uuid=self.kwargs["organization_uuid"])
        channel = get_object_or_404(Channel, organization=organization, uuid=self.kwargs["channel_uuid"])
        return channel

    def get_queryset(self):
        channel = self._channel()
        ensure_org_channel_permission(self.request.user, channel.organization, "channels:grants")
        return ChannelAccessGrant.objects.filter(channel=channel)

    def get_serializer_class(self):
        if self.action == "create":
            return ChannelAccessGrantCreateSerializer
        return ChannelAccessGrantSerializer

    def perform_create(self, serializer):
        channel = self._channel()
        ensure_org_channel_permission(self.request.user, channel.organization, "channels:grants")
        data = serializer.validated_data
        ChannelAccessGrant.objects.create(
            channel=channel,
            organization=channel.organization,
            subject_type=data["subject_type"],
            subject_user=data.get("subject_user"),
            subject_team=data.get("subject_team"),
            permissions=sorted({perm for perm in data["permissions"]}),
            granted_by=self.request.user,
        )

    def destroy(self, request, *args, **kwargs):
        grant = self.get_object()
        ensure_org_channel_permission(request.user, grant.organization, "channels:grants")
        grant.revoke(actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChannelTypeListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, organization_uuid: str):
        organization = get_object_or_404(Organization, uuid=organization_uuid)
        ensure_org_channel_permission(request.user, organization, "channels:read")
        data = []
        for channel_type, label in CHANNEL_TYPE_CHOICES:
            data.append(
                {
                    "channelTypeId": channel_type,
                    "name": label,
                    "schema": list(CHANNEL_CONFIGURATION_SCHEMAS[channel_type].keys()),
                }
            )
        return Response(data, status=status.HTTP_200_OK)


class ChannelTypeEnabledView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, organization_uuid: str):
        organization = get_object_or_404(Organization, uuid=organization_uuid)
        ensure_org_channel_permission(request.user, organization, "channels:read")
        limits = resolve_channel_limits(organization)
        data = [
            {
                "channelTypeId": channel_type,
                "enabled": limit.enabled,
                "maxInstances": limit.max_instances,
            }
            for channel_type, limit in limits.items()
        ]
        return Response(data, status=status.HTTP_200_OK)
