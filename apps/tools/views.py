from __future__ import annotations

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.agents.definitions import get_tool_definition, list_tool_definitions
from apps.agents.models import OrganizationEnabledTool
from apps.organizations.models import Organization
from apps.tools.serializers import (
    OrganizationEnabledToolSerializer,
    ToolDefinitionSerializer,
    ToolValidationSerializer,
)
from apps.tools.services import (
    disable_tool,
    enable_tool,
    ensure_tool_permission,
    validate_tool_configuration,
)


class ToolDefinitionListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses=ToolDefinitionSerializer(many=True))
    def get(self, request):
        definitions = list_tool_definitions()
        payload = [
            {
                "toolKey": definition.key,
                "displayName": definition.display_name,
                "description": definition.description,
                "categories": definition.raw.get("categories", []),
            }
            for definition in definitions
        ]
        serializer = ToolDefinitionSerializer(payload, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ToolDefinitionDetailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses=ToolDefinitionSerializer)
    def get(self, request, tool_key: str):
        definition = get_tool_definition(tool_key)
        if not definition:
            return Response({"code": "TOOL_NOT_FOUND", "message": "Unknown tool key."}, status=status.HTTP_404_NOT_FOUND)
        data = {
            "toolKey": definition.key,
            "displayName": definition.display_name,
            "description": definition.description,
            "categories": definition.raw.get("categories", []),
        }
        return Response(ToolDefinitionSerializer(data).data, status=status.HTTP_200_OK)


class ToolSchemaView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, tool_key: str):
        definition = get_tool_definition(tool_key)
        if not definition:
            return Response({"code": "TOOL_NOT_FOUND", "message": "Unknown tool key."}, status=status.HTTP_404_NOT_FOUND)
        schema = definition.raw.get("configurationSchema") or {}
        return Response(schema, status=status.HTTP_200_OK)


class ToolValidationView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=ToolValidationSerializer, responses=ToolValidationSerializer)
    def post(self, request):
        serializer = ToolValidationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = get_object_or_404(Organization, uuid=serializer.validated_data["organization_uuid"])
        ensure_tool_permission(request.user, organization, "tools:read")
        validated = validate_tool_configuration(serializer.validated_data, organization=organization)
        return Response(validated, status=status.HTTP_200_OK)


class OrganizationToolViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = OrganizationEnabledToolSerializer

    def _organization(self):
        if not hasattr(self, "_cached_org"):
            self._cached_org = get_object_or_404(Organization, uuid=self.kwargs["organization_uuid"])
        return self._cached_org

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return OrganizationEnabledTool.objects.none()
        organization = self._organization()
        ensure_tool_permission(self.request.user, organization, "tools:read")
        return OrganizationEnabledTool.objects.filter(organization=organization, disabled_at__isnull=True)


class OrganizationToolEnableView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, organization_uuid: str, tool_key: str):
        organization = get_object_or_404(Organization, uuid=organization_uuid)
        ensure_tool_permission(request.user, organization, "tools:enable")
        record = enable_tool(organization, tool_key, request.user)
        serializer = OrganizationEnabledToolSerializer(record)
        return Response(serializer.data, status=status.HTTP_200_OK)


class OrganizationToolDisableView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, organization_uuid: str, tool_key: str):
        organization = get_object_or_404(Organization, uuid=organization_uuid)
        ensure_tool_permission(request.user, organization, "tools:disable")
        record = disable_tool(organization, tool_key, request.user)
        serializer = OrganizationEnabledToolSerializer(record)
        return Response(serializer.data, status=status.HTTP_200_OK)

