from __future__ import annotations

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.agents.definitions import get_tool_definition, list_tool_definitions
from apps.agents.models import OrganizationEnabledTool
from apps.organizations.models import Organization
from apps.tools.serializers import OrganizationEnabledToolSerializer, ToolDefinitionSerializer
from apps.tools.services import disable_tool, enable_tool, ensure_tool_permission, validate_tool_configuration
from apps.tools.telemetry import inc_tool_list, inc_tool_validation
from apps.tools.usage import agents_usage_by_tool_keys


def _tool_payload(definition, *, used_by_agents: int = 0):
    return {
        "toolKey": definition.key,
        "displayName": definition.display_name,
        "description": definition.description,
        "category": definition.raw.get("category", ""),
        "configurationSchema": definition.raw.get("configurationSchema") or {},
        "usedByAgents": used_by_agents,
    }


class OrganizationToolListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=ToolDefinitionSerializer(many=True))
    def get(self, request, organization_uuid: str):
        organization = get_object_or_404(Organization, uuid=organization_uuid)
        ensure_tool_permission(request.user, organization, "tools:list")
        definitions = list_tool_definitions()
        category = request.query_params.get("category")
        if category:
            definitions = [d for d in definitions if d.raw.get("category") == category]
        tool_keys = [definition.key for definition in definitions]
        usage = agents_usage_by_tool_keys(organization, tool_keys)
        payload = [
            _tool_payload(definition, used_by_agents=usage.get(definition.key, 0))
            for definition in definitions
        ]
        inc_tool_list()
        serializer = ToolDefinitionSerializer(payload, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class OrganizationToolDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=ToolDefinitionSerializer)
    def get(self, request, organization_uuid: str, tool_key: str):
        organization = get_object_or_404(Organization, uuid=organization_uuid)
        ensure_tool_permission(request.user, organization, "tools:list")
        definition = get_tool_definition(tool_key)
        if not definition:
            return Response({"code": "TOOL_NOT_FOUND", "message": "Unknown tool key."}, status=status.HTTP_404_NOT_FOUND)
        usage = agents_usage_by_tool_keys(organization, [definition.key]).get(definition.key, 0)
        payload = _tool_payload(definition, used_by_agents=usage)
        serializer = ToolDefinitionSerializer(payload)
        return Response(serializer.data, status=status.HTTP_200_OK)


class OrganizationToolEnabledListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=ToolDefinitionSerializer(many=True))
    def get(self, request, organization_uuid: str):
        organization = get_object_or_404(Organization, uuid=organization_uuid)
        ensure_tool_permission(request.user, organization, "tools:read")
        enabled = list(
            OrganizationEnabledTool.objects.filter(organization=organization, disabled_at__isnull=True)
        )
        definitions = {d.key: d for d in list_tool_definitions()}
        tool_keys = [row.tool_key for row in enabled]
        usage = agents_usage_by_tool_keys(organization, tool_keys)
        payload = []
        for row in enabled:
            definition = definitions.get(row.tool_key)
            if not definition:
                continue
            payload.append(_tool_payload(definition, used_by_agents=usage.get(definition.key, 0)))
        inc_tool_list()
        serializer = ToolDefinitionSerializer(payload, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class OrganizationToolEnableView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, organization_uuid: str, tool_key: str):
        organization = get_object_or_404(Organization, uuid=organization_uuid)
        ensure_tool_permission(request.user, organization, "tools:enable")
        record = enable_tool(organization, tool_key, request.user)
        definition = get_tool_definition(tool_key)
        usage = agents_usage_by_tool_keys(organization, [tool_key]).get(tool_key, 0)
        data = OrganizationEnabledToolSerializer(record).data
        if definition:
            data.update(
                {
                    "description": definition.description,
                    "configurationSchema": definition.raw.get("configurationSchema") or {},
                }
            )
        data["usedByAgents"] = usage
        return Response(data, status=status.HTTP_200_OK)


class OrganizationToolDisableView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, organization_uuid: str, tool_key: str):
        organization = get_object_or_404(Organization, uuid=organization_uuid)
        ensure_tool_permission(request.user, organization, "tools:disable")
        record = disable_tool(organization, tool_key, request.user)
        definition = get_tool_definition(tool_key)
        usage = agents_usage_by_tool_keys(organization, [record.tool_key]).get(record.tool_key, 0)
        warning = None
        if usage > 0:
            warning = f"{usage} agent(s) currently use this tool. Disabling will hide it from new configs."
        data = OrganizationEnabledToolSerializer(record).data
        if definition:
            data.update(
                {
                    "description": definition.description,
                    "configurationSchema": definition.raw.get("configurationSchema") or {},
                }
            )
        data["usedByAgents"] = usage
        data["warning"] = warning
        return Response(data, status=status.HTTP_200_OK)


class ToolValidateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        organization_uuid = request.data.get("organization_uuid") or request.data.get("organizationId")
        if not organization_uuid:
            return Response(
                {"code": "ORGANIZATION_NOT_FOUND", "message": "organization_uuid is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        organization = get_object_or_404(Organization, uuid=organization_uuid)
        ensure_tool_permission(request.user, organization, "tools:read")
        payload = {
            "toolKey": request.data.get("toolKey") or request.data.get("tool_key"),
            "configuration": request.data.get("configuration") or {},
        }
        try:
            validated = validate_tool_configuration(payload, organization=organization)
        except Exception:
            inc_tool_validation(False)
            raise
        inc_tool_validation(True)
        return Response(validated, status=status.HTTP_200_OK)
