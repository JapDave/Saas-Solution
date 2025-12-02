from __future__ import annotations

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.agents.definitions import list_llm_definitions, list_tool_definitions
from apps.agents.models import Agent, AgentVersion, OrganizationEnabledLLM, OrganizationEnabledTool
from apps.agents.serializers import (
    AgentReadSerializer,
    AgentVersionCreateSerializer,
    AgentVersionSerializer,
    AgentWriteSerializer,
    LLMEnableSerializer,
    OrganizationEnabledLLMSerializer,
    OrganizationEnabledToolSerializer,
    ToolEnableSerializer,
)
from apps.agents.services import (
    clone_agent,
    disable_llm_for_organization,
    disable_tool_for_organization,
    enable_llm_for_organization,
    enable_tool_for_organization,
    enforce_agent_creation_limit,
    ensure_agent_permission,
    filter_agents_for_user,
    save_agent_version,
)
from apps.common.exceptions import CustomError, INVALID_STATE_TRANSITION
from apps.common.serializers import ErrorSerializer
from apps.organizations.models import Organization


@extend_schema(
    tags=["Agents"],
    responses={400: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer, 409: ErrorSerializer, 500: ErrorSerializer},
    description=(
        "Conversational agents for an organization.\n\n"
        "Permissions:\n"
        "- List/Read: agents:read\n"
        "- Create/Update: agents:create / agents:update\n"
        "- Delete: agents:delete\n"
        "- Versioning: agents:versions:save / agents:versions:switch\n"
    ),
)
class AgentViewSet(viewsets.ModelViewSet):
    queryset = Agent.objects.select_related("organization", "current_version").prefetch_related("versions")
    permission_classes = [IsAuthenticated]
    lookup_field = "uuid"
    ERROR_DOMAIN = "agents"

    def get_queryset(self):
        queryset = filter_agents_for_user(self.queryset, getattr(self.request, "user", None))
        org_uuid = self.request.query_params.get("organization_uuid")
        if org_uuid:
            queryset = queryset.filter(organization__uuid=org_uuid)
        state = self.request.query_params.get("state")
        if state:
            queryset = queryset.filter(state=state)
        return queryset.order_by("-created_at")

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return AgentWriteSerializer
        return AgentReadSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        agent = self._save_agent(serializer, request.user)
        read = AgentReadSerializer(agent, context=self.get_serializer_context())
        headers = self.get_success_headers(read.data)
        return Response(read.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        ensure_agent_permission(request.user, instance.organization, "agents:update")
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        agent = serializer.save(updated_by=request.user)
        read = AgentReadSerializer(agent, context=self.get_serializer_context())
        return Response(read.data)

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def _save_agent(self, serializer, user):
        organization = serializer.validated_data["organization"]
        ensure_agent_permission(user, organization, "agents:create")
        enforce_agent_creation_limit(organization)
        return serializer.save(
            state=Agent.AgentState.DRAFT,
            created_by=user,
            updated_by=user,
        )

    def perform_destroy(self, instance):
        ensure_agent_permission(self.request.user, instance.organization, "agents:delete")
        instance.state = Agent.AgentState.DELETED
        instance.updated_by = self.request.user
        instance.save(update_fields=["state", "updated_by", "updated_at"])
        super().perform_destroy(instance)

    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, uuid=None):
        agent = self.get_object()
        ensure_agent_permission(request.user, agent.organization, "agents:update")
        self._transition(agent, Agent.AgentState.ACTIVE)
        return Response(AgentReadSerializer(agent).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="archive")
    def archive(self, request, uuid=None):
        agent = self.get_object()
        ensure_agent_permission(request.user, agent.organization, "agents:update")
        self._transition(agent, Agent.AgentState.ARCHIVED)
        return Response(AgentReadSerializer(agent).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="restore")
    def restore(self, request, uuid=None):
        agent = self.get_object()
        ensure_agent_permission(request.user, agent.organization, "agents:update")
        if agent.state != Agent.AgentState.ARCHIVED:
            raise CustomError(code=INVALID_STATE_TRANSITION, status_code=400, detail="Only archived agents can restore.")
        self._transition(agent, Agent.AgentState.ACTIVE)
        agent.deleted_at = None
        agent.save(update_fields=["deleted_at", "updated_at"])
        return Response(AgentReadSerializer(agent).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="clone")
    def clone(self, request, uuid=None):
        agent = self.get_object()
        ensure_agent_permission(request.user, agent.organization, "agents:clone")
        clone = clone_agent(agent, created_by=request.user)
        return Response(AgentReadSerializer(clone).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get", "post"], url_path="versions")
    def versions(self, request, uuid=None):
        agent = self.get_object()
        if request.method.lower() == "get":
            ensure_agent_permission(request.user, agent.organization, "agents:read")
            serializer = AgentVersionSerializer(agent.versions.order_by("-version_number"), many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        ensure_agent_permission(request.user, agent.organization, "agents:versions:save")
        payload = AgentVersionCreateSerializer(data=request.data, context={"agent": agent})
        payload.is_valid(raise_exception=True)
        updates = payload.validated_data
        for field in ["name", "description", "system_prompts", "llm_configuration", "tools_configuration"]:
            if field in updates:
                setattr(agent, field, updates[field])
        agent.updated_by = request.user
        agent.save()
        version = save_agent_version(agent, actor=request.user)
        return Response(AgentVersionSerializer(version).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path=r"versions/(?P<version_uuid>[^/]+)")
    def version_detail(self, request, uuid=None, version_uuid=None):
        agent = self.get_object()
        ensure_agent_permission(request.user, agent.organization, "agents:read")
        version = get_object_or_404(agent.versions, uuid=version_uuid)
        return Response(AgentVersionSerializer(version).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path=r"versions/(?P<version_uuid>[^/]+)/switch")
    def version_switch(self, request, uuid=None, version_uuid=None):
        agent = self.get_object()
        ensure_agent_permission(request.user, agent.organization, "agents:versions:switch")
        version = get_object_or_404(agent.versions, uuid=version_uuid)
        agent.current_version = version
        agent.updated_by = request.user
        agent.save(update_fields=["current_version", "updated_by", "updated_at"])
        return Response(AgentReadSerializer(agent).data, status=status.HTTP_200_OK)

    def _transition(self, agent: Agent, target_state: str):
        valid_transitions = {
            Agent.AgentState.DRAFT: {Agent.AgentState.ACTIVE, Agent.AgentState.DELETED},
            Agent.AgentState.ACTIVE: {Agent.AgentState.ARCHIVED, Agent.AgentState.DELETED},
            Agent.AgentState.ARCHIVED: {Agent.AgentState.ACTIVE, Agent.AgentState.DELETED},
        }
        allowed = valid_transitions.get(agent.state, set())
        if target_state not in allowed:
            raise CustomError(code=INVALID_STATE_TRANSITION, status_code=400, detail="Invalid state transition.")
        agent.state = target_state
        agent.updated_by = self.request.user
        agent.save(update_fields=["state", "updated_by", "updated_at"])


class OrganizationLLMAvailableView(APIView):
    permission_classes = [IsAuthenticated]
    ERROR_DOMAIN = "agents"

    @extend_schema(
        responses={200: OrganizationEnabledLLMSerializer(many=True), 400: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
        description=(
            "List available LLM definitions and configuration schemas for an organization. "
            "Requires permission: agents:read."
        ),
    )
    def get(self, request, organization_uuid: str):
        organization = get_object_or_404(Organization, uuid=organization_uuid)
        ensure_agent_permission(request.user, organization, "agents:read")
        enabled = set(
            OrganizationEnabledLLM.objects.filter(
                organization=organization,
                disabled_at__isnull=True,
            ).values_list("model_key", flat=True)
        )
        data = []
        for definition in list_llm_definitions():
            data.append(
                {
                    "modelKey": definition.key,
                    "modelProvider": definition.provider,
                    "displayName": definition.display_name,
                    "description": definition.description,
                    "requiresHostedSubscription": definition.requires_hosted_subscription,
                    "enabled": definition.key in enabled,
                    "configurationSchema": definition.raw.get("modelConfiguration", {}),
                }
            )
        return Response(data, status=status.HTTP_200_OK)


class OrganizationLLMView(APIView):
    permission_classes = [IsAuthenticated]
    ERROR_DOMAIN = "agents"

    def get_organization(self, organization_uuid):
        return get_object_or_404(Organization, uuid=organization_uuid)

    @extend_schema(
        responses={200: OrganizationEnabledLLMSerializer(many=True), 400: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
        description="List enabled LLMs for an organization. Requires permission: agents:llms:enable.",
    )
    def get(self, request, organization_uuid: str):
        organization = self.get_organization(organization_uuid)
        ensure_agent_permission(request.user, organization, "agents:llms:enable")
        qs = OrganizationEnabledLLM.objects.filter(organization=organization, disabled_at__isnull=True)
        serializer = OrganizationEnabledLLMSerializer(qs, many=True)
        return Response(serializer.data)

    @extend_schema(
        request=LLMEnableSerializer,
        responses={201: OrganizationEnabledLLMSerializer, 400: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
        description="Enable an LLM for an organization. Requires permission: agents:llms:enable.",
    )
    def post(self, request, organization_uuid: str):
        serializer = LLMEnableSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = self.get_organization(organization_uuid)
        ensure_agent_permission(request.user, organization, "agents:llms:enable")
        record = enable_llm_for_organization(
            organization=organization,
            model_key=serializer.validated_data["model_key"],
            actor=request.user,
        )
        return Response(OrganizationEnabledLLMSerializer(record).data, status=status.HTTP_201_CREATED)


class OrganizationLLMDisableView(APIView):
    permission_classes = [IsAuthenticated]
    ERROR_DOMAIN = "agents"

    @extend_schema(
        responses={200: OrganizationEnabledLLMSerializer, 400: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
        description="Disable an LLM for an organization. Requires permission: agents:llms:enable.",
    )
    def post(self, request, organization_uuid: str, model_key: str):
        organization = get_object_or_404(Organization, uuid=organization_uuid)
        ensure_agent_permission(request.user, organization, "agents:llms:enable")
        record = disable_llm_for_organization(organization=organization, model_key=model_key, actor=request.user)
        return Response(OrganizationEnabledLLMSerializer(record).data, status=status.HTTP_200_OK)


class OrganizationToolAvailableView(APIView):
    permission_classes = [IsAuthenticated]
    ERROR_DOMAIN = "agents"

    @extend_schema(
        responses={200: OrganizationEnabledToolSerializer(many=True), 400: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
        description=(
            "List available tools and configuration schemas for an organization. "
            "Requires permission: agents:read."
        ),
    )
    def get(self, request, organization_uuid: str):
        organization = get_object_or_404(Organization, uuid=organization_uuid)
        ensure_agent_permission(request.user, organization, "agents:read")
        enabled = set(
            OrganizationEnabledTool.objects.filter(
                organization=organization,
                disabled_at__isnull=True,
            ).values_list("tool_key", flat=True)
        )
        data = []
        for definition in list_tool_definitions():
            data.append(
                {
                    "toolKey": definition.key,
                    "displayName": definition.display_name,
                    "description": definition.description,
                    "enabled": definition.key in enabled,
                    "configurationSchema": definition.raw.get("configurationSchema", {}),
                }
            )
        return Response(data, status=status.HTTP_200_OK)


class OrganizationToolView(APIView):
    permission_classes = [IsAuthenticated]
    ERROR_DOMAIN = "agents"

    @extend_schema(
        responses={200: OrganizationEnabledToolSerializer(many=True), 400: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
        description="List enabled tools for an organization. Requires permission: agents:tools:enable.",
    )
    def get(self, request, organization_uuid: str):
        organization = get_object_or_404(Organization, uuid=organization_uuid)
        ensure_agent_permission(request.user, organization, "agents:tools:enable")
        qs = OrganizationEnabledTool.objects.filter(organization=organization, disabled_at__isnull=True)
        serializer = OrganizationEnabledToolSerializer(qs, many=True)
        return Response(serializer.data)

    @extend_schema(
        request=ToolEnableSerializer,
        responses={201: OrganizationEnabledToolSerializer, 400: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
        description="Enable a tool for an organization. Requires permission: agents:tools:enable.",
    )
    def post(self, request, organization_uuid: str):
        serializer = ToolEnableSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = get_object_or_404(Organization, uuid=organization_uuid)
        ensure_agent_permission(request.user, organization, "agents:tools:enable")
        record = enable_tool_for_organization(
            organization=organization,
            tool_key=serializer.validated_data["tool_key"],
            actor=request.user,
        )
        return Response(OrganizationEnabledToolSerializer(record).data, status=status.HTTP_201_CREATED)


class OrganizationToolDisableView(APIView):
    permission_classes = [IsAuthenticated]
    ERROR_DOMAIN = "agents"

    @extend_schema(
        responses={200: OrganizationEnabledToolSerializer, 400: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
        description="Disable a tool for an organization. Requires permission: agents:tools:enable.",
    )
    def post(self, request, organization_uuid: str, tool_key: str):
        organization = get_object_or_404(Organization, uuid=organization_uuid)
        ensure_agent_permission(request.user, organization, "agents:tools:enable")
        record = disable_tool_for_organization(organization=organization, tool_key=tool_key, actor=request.user)
        return Response(OrganizationEnabledToolSerializer(record).data, status=status.HTTP_200_OK)
