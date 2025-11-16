from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.exceptions import CustomError, FLOW_VERSION_NOT_FOUND
from apps.flows.models import Flow, FlowVersion
from apps.flows.serializers import (
    FlowCreateSerializer,
    FlowDetailSerializer,
    FlowReadSerializer,
    FlowUpdateSerializer,
    FlowVersionCreateSerializer,
    FlowVersionDetailSerializer,
    FlowVersionSummarySerializer,
)
from apps.flows.services import (
    clone_flow,
    create_draft_from_published,
    delete_flow,
    disable_flow,
    enable_flow,
    ensure_flow_permission,
    publish_flow,
    restore_flow,
)
from apps.organizations.models import Organization


class FlowViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    lookup_field = "uuid"

    def _organization(self) -> Organization:
        if not hasattr(self, "_cached_org"):
            self._cached_org = get_object_or_404(Organization, uuid=self.kwargs["organization_uuid"])
        return self._cached_org

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Flow.objects.none()
        organization = self._organization()
        include_deleted = self.request.query_params.get("includeDeleted") == "true"
        base_qs = Flow.all_objects if include_deleted else Flow.objects
        queryset = base_qs.filter(organization=organization).prefetch_related("versions", "versions__created_by")
        state = self.request.query_params.get("state")
        if state:
            queryset = queryset.filter(versions__state=state.lower(), versions__is_active=True).distinct()
        return queryset.order_by("-updated_at")

    def get_object(self):
        organization = self._organization()
        queryset = Flow.all_objects.filter(organization=organization).prefetch_related("versions", "versions__created_by")
        flow = get_object_or_404(queryset, uuid=self.kwargs["uuid"])
        return flow

    def get_serializer_class(self):
        if self.action == "create":
            return FlowCreateSerializer
        if self.action in {"update", "partial_update"}:
            return FlowUpdateSerializer
        if self.action == "retrieve":
            return FlowDetailSerializer
        return FlowReadSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["organization"] = self._organization()
        return context

    def list(self, request, *args, **kwargs):
        ensure_flow_permission(request.user, self._organization(), "agents:flows:read")
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        ensure_flow_permission(request.user, self._organization(), "agents:flows:read")
        return super().retrieve(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        ensure_flow_permission(request.user, self._organization(), "agents:flows:create")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        flow = serializer.save()
        read = FlowDetailSerializer(flow, context=self.get_serializer_context())
        headers = self.get_success_headers(read.data)
        return Response(read.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        ensure_flow_permission(request.user, self._organization(), "agents:flows:update")
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        flow = serializer.save()
        read = FlowDetailSerializer(flow, context=self.get_serializer_context())
        return Response(read.data)

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        ensure_flow_permission(request.user, self._organization(), "agents:flows:delete")
        flow = self.get_object()
        delete_flow(flow, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="restore")
    def restore(self, request, *args, **kwargs):
        ensure_flow_permission(request.user, self._organization(), "agents:flows:delete")
        flow = self.get_object()
        restore_flow(flow, actor=request.user)
        serializer = FlowDetailSerializer(flow, context=self.get_serializer_context())
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="clone")
    def clone(self, request, *args, **kwargs):
        ensure_flow_permission(request.user, self._organization(), "agents:flows:clone")
        flow = self.get_object()
        cloned = clone_flow(flow, actor=request.user)
        serializer = FlowDetailSerializer(cloned, context=self.get_serializer_context())
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="publish")
    def publish(self, request, *args, **kwargs):
        ensure_flow_permission(request.user, self._organization(), "agents:flows:publish")
        flow = self.get_object()
        version = publish_flow(flow, actor=request.user)
        return Response(FlowVersionDetailSerializer(version).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="disable")
    def disable(self, request, *args, **kwargs):
        ensure_flow_permission(request.user, self._organization(), "agents:flows:disable")
        flow = self.get_object()
        version = disable_flow(flow, actor=request.user)
        return Response(FlowVersionDetailSerializer(version).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="enable")
    def enable(self, request, *args, **kwargs):
        ensure_flow_permission(request.user, self._organization(), "agents:flows:enable")
        flow = self.get_object()
        version = enable_flow(flow, actor=request.user)
        return Response(FlowVersionDetailSerializer(version).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="create-draft")
    def create_draft(self, request, *args, **kwargs):
        ensure_flow_permission(request.user, self._organization(), "agents:flows:update")
        flow = self.get_object()
        version = create_draft_from_published(flow, actor=request.user)
        return Response(FlowVersionDetailSerializer(version).data, status=status.HTTP_201_CREATED)


class FlowVersionViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    lookup_field = "version_number"
    lookup_value_regex = r"[0-9]+"

    def _organization(self):
        if not hasattr(self, "_cached_org"):
            self._cached_org = get_object_or_404(Organization, uuid=self.kwargs["organization_uuid"])
        return self._cached_org

    def _flow(self) -> Flow:
        if not hasattr(self, "_cached_flow"):
            organization = self._organization()
            self._cached_flow = get_object_or_404(
                Flow.all_objects.prefetch_related("versions", "versions__created_by"),
                uuid=self.kwargs["flow_uuid"],
                organization=organization,
            )
        return self._cached_flow

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return FlowVersion.objects.none()
        flow = self._flow()
        ensure_flow_permission(self.request.user, flow.organization, "agents:flows:versions:read")
        return flow.versions.all().order_by("-version_number")

    def get_serializer_class(self):
        if self.action == "create":
            return FlowVersionCreateSerializer
        if self.action == "retrieve":
            return FlowVersionDetailSerializer
        return FlowVersionSummarySerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["flow"] = self._flow()
        context["organization"] = self._organization()
        return context

    def list(self, request, *args, **kwargs):
        ensure_flow_permission(request.user, self._organization(), "agents:flows:versions:read")
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        ensure_flow_permission(request.user, self._organization(), "agents:flows:versions:read")
        return super().retrieve(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        ensure_flow_permission(request.user, self._organization(), "agents:flows:update")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        version = serializer.save()
        read = FlowVersionDetailSerializer(version, context=self.get_serializer_context())
        return Response(read.data, status=status.HTTP_201_CREATED)

    def get_object(self):
        flow = self._flow()
        version_number = int(self.kwargs["version_number"])
        version = flow.versions.filter(version_number=version_number).first()
        if not version:
            raise CustomError(code=FLOW_VERSION_NOT_FOUND, status_code=404, detail="Version not found.")
        return version
