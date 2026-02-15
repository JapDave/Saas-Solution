from __future__ import annotations

from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.agents.definitions import list_llm_definitions, list_tool_definitions
from apps.agents.models import Agent, AgentVersion, OrganizationEnabledLLM, OrganizationEnabledTool
from apps.agents.serializers import (
    AgentCreateSerializer,
    AgentPatchSerializer,
    AgentReadSerializer,
    AgentVersionCreateSerializer,
    AgentVersionSerializer,
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
    ensure_agent_subscription,
    ensure_agent_name_unique,
    save_agent_version,
)
from apps.agents.telemetry import (
    inc_agent_updates,
    inc_agent_versions_saved,
    inc_agent_versions_switched,
    inc_agents_cloned,
    inc_agents_created,
    inc_agents_deleted,
)
from apps.common.exceptions import (
    AGENT_VERSION_NOT_FOUND,
    AGENT_NAME_NOT_UNIQUE,
    CustomError,
    INVALID_STATE_TRANSITION,
)
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
    lookup_url_kwarg = "agent_id"
    ERROR_DOMAIN = "agents"
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return self.queryset.order_by("-created_at")

    def get_serializer_class(self):
        if self.action == "create":
            return AgentCreateSerializer
        if self.action in {"update", "partial_update"}:
            return AgentPatchSerializer
        return AgentReadSerializer

    def get_object(self):
        return self._get_agent(include_deleted=False)

    def _get_organization(self):
        organization_uuid = self.kwargs.get("organization_id")
        if not organization_uuid:
            raise CustomError(code="ORGANIZATION_NOT_FOUND", status_code=404, detail="Organization not found.")
        organization = get_object_or_404(Organization, uuid=organization_uuid)
        ensure_agent_subscription(organization)
        return organization

    def _get_agent(self, *, include_deleted: bool = False) -> Agent:
        organization = self._get_organization()
        qs = Agent.all_objects if include_deleted else Agent.objects
        agent = get_object_or_404(qs.filter(organization=organization), uuid=self.kwargs.get("agent_id"))
        return agent

    def list(self, request, *args, **kwargs):
        organization = self._get_organization()
        ensure_agent_permission(request.user, organization, "agents:read")
        qs = Agent.objects.filter(organization=organization).order_by("-created_at")
        state = request.query_params.get("state")
        if state:
            qs = qs.filter(state=state)
        page = self.paginate_queryset(qs)
        serializer = AgentReadSerializer(page or qs, many=True, context=self.get_serializer_context())
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        organization = self._get_organization()
        ensure_agent_permission(request.user, organization, "agents:read")
        agent = self._get_agent(include_deleted=False)
        return Response(AgentReadSerializer(agent).data, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        organization = self._get_organization()
        ensure_agent_permission(request.user, organization, "agents:create")
        enforce_agent_creation_limit(organization)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        name = serializer.validated_data["name"]
        description = serializer.validated_data.get("description", "")
        ensure_agent_name_unique(organization=organization, name=name)
        agent = Agent(
            organization=organization,
            name=name,
            description=description,
            state=Agent.AgentState.DRAFT,
            created_by=request.user,
            updated_by=request.user,
        )
        # guard against concurrent duplicates
        try:
            agent.save()
        except IntegrityError:
            raise CustomError(code=AGENT_NAME_NOT_UNIQUE, status_code=409, detail="Agent name already exists in organization.")
        inc_agents_created()
        read = AgentReadSerializer(agent, context=self.get_serializer_context())
        headers = self.get_success_headers(read.data)
        return Response(read.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        return Response({"code": "METHOD_NOT_ALLOWED", "message": "Use PATCH to update agents."}, status=405)

    def partial_update(self, request, *args, **kwargs):
        organization = self._get_organization()
        ensure_agent_permission(request.user, organization, "agents:update")
        agent = self._get_agent(include_deleted=False)
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if agent.state in {Agent.AgentState.ARCHIVED, Agent.AgentState.DELETED}:
            blocked_fields = {"name", "description", "current_version_id"}
            if blocked_fields & set(data.keys()):
                raise CustomError(
                    code=INVALID_STATE_TRANSITION,
                    status_code=400,
                    detail="Archived or deleted agents are read-only.",
                )

        if "name" in data:
            ensure_agent_name_unique(organization=organization, name=data["name"], exclude_agent=agent)
            agent.name = data["name"]
        if "description" in data:
            agent.description = data["description"]

        if "current_version_id" in data:
            version = agent.versions.filter(uuid=data["current_version_id"]).first()
            if not version:
                raise CustomError(code=AGENT_VERSION_NOT_FOUND, status_code=404, detail="Version not found.")
            agent.current_version = version
            agent.system_prompts = version.system_prompts
            agent.llm_configuration = version.llm_configuration
            agent.tools_configuration = version.tools_configuration

        if "state" in data:
            self._transition(agent, data["state"])

        agent.updated_by = request.user
        agent.save(update_fields=[
            "name",
            "description",
            "current_version",
            "system_prompts",
            "llm_configuration",
            "tools_configuration",
            "state",
            "updated_by",
            "updated_at",
        ])
        inc_agent_updates()
        read = AgentReadSerializer(agent, context=self.get_serializer_context())
        return Response(read.data, status=status.HTTP_200_OK)

    def perform_destroy(self, instance):
        ensure_agent_permission(self.request.user, instance.organization, "agents:delete")
        instance.state = Agent.AgentState.DELETED
        instance.deleted_at = timezone.now()
        instance.updated_by = self.request.user
        instance.save(update_fields=["state", "deleted_at", "updated_by", "updated_at"])
        inc_agents_deleted()

    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, uuid=None):
        agent = self._get_agent(include_deleted=False)
        ensure_agent_permission(request.user, agent.organization, "agents:update")
        if agent.state != Agent.AgentState.DRAFT:
            raise CustomError(
                code=INVALID_STATE_TRANSITION,
                status_code=400,
                detail="Only draft agents can be activated.",
            )
        self._transition(agent, Agent.AgentState.ACTIVE)
        inc_agent_updates()
        return Response(AgentReadSerializer(agent).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="archive")
    def archive(self, request, uuid=None):
        agent = self._get_agent(include_deleted=False)
        ensure_agent_permission(request.user, agent.organization, "agents:update")
        if agent.state != Agent.AgentState.ACTIVE:
            raise CustomError(
                code=INVALID_STATE_TRANSITION,
                status_code=400,
                detail="Only active agents can be archived.",
            )
        self._transition(agent, Agent.AgentState.ARCHIVED)
        inc_agent_updates()
        return Response(AgentReadSerializer(agent).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="restore")
    def restore(self, request, uuid=None):
        agent = self._get_agent(include_deleted=True)
        ensure_agent_permission(request.user, agent.organization, "agents:update")
        if agent.state not in {Agent.AgentState.ARCHIVED, Agent.AgentState.DELETED}:
            raise CustomError(code=INVALID_STATE_TRANSITION, status_code=400, detail="Only archived/deleted agents can restore.")
        target_state = Agent.AgentState.ACTIVE if agent.state == Agent.AgentState.ARCHIVED else Agent.AgentState.DRAFT
        self._transition(agent, target_state)
        agent.deleted_at = None
        agent.save(update_fields=["deleted_at", "updated_at"])
        inc_agent_updates()
        return Response(AgentReadSerializer(agent).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="clone")
    def clone(self, request, uuid=None):
        agent = self._get_agent(include_deleted=False)
        ensure_agent_permission(request.user, agent.organization, "agents:clone")
        enforce_agent_creation_limit(agent.organization)
        clone = clone_agent(agent, created_by=request.user)
        inc_agents_cloned()
        return Response(AgentReadSerializer(clone).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get", "post"], url_path="versions")
    def versions(self, request, uuid=None):
        agent = self._get_agent(include_deleted=True)
        if request.method.lower() == "get":
            ensure_agent_permission(request.user, agent.organization, "agents:read")
            serializer = AgentVersionSerializer(agent.versions.order_by("-version_number"), many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        ensure_agent_permission(request.user, agent.organization, "agents:versions:save")
        if agent.state in {Agent.AgentState.ARCHIVED, Agent.AgentState.DELETED}:
            raise CustomError(
                code=INVALID_STATE_TRANSITION,
                status_code=400,
                detail="Cannot save versions for archived or deleted agents.",
            )
        payload = AgentVersionCreateSerializer(data=request.data, context={"agent": agent})
        payload.is_valid(raise_exception=True)
        updates = payload.validated_data
        if "name" in updates:
            ensure_agent_name_unique(organization=agent.organization, name=updates["name"], exclude_agent=agent)
        version, created = save_agent_version(
            agent,
            actor=request.user,
            name=updates.get("name"),
            description=updates.get("description"),
            system_prompts=updates.get("system_prompts"),
            llm_configuration=updates.get("llm_configuration"),
            tools_configuration=updates.get("tools_configuration"),
        )
        if created:
            inc_agent_versions_saved()
        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(AgentVersionSerializer(version).data, status=status_code)

    @action(detail=True, methods=["get"], url_path=r"versions/(?P<version_uuid>[^/]+)")
    def version_detail(self, request, uuid=None, version_uuid=None):
        agent = self._get_agent(include_deleted=True)
        ensure_agent_permission(request.user, agent.organization, "agents:read")
        version = agent.versions.filter(uuid=version_uuid).first()
        if not version:
            raise CustomError(code=AGENT_VERSION_NOT_FOUND, status_code=404, detail="Version not found.")
        return Response(AgentVersionSerializer(version).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path=r"versions/(?P<version_uuid>[^/]+)/switch")
    def version_switch(self, request, uuid=None, version_uuid=None):
        agent = self._get_agent(include_deleted=True)
        ensure_agent_permission(request.user, agent.organization, "agents:versions:switch")
        version = agent.versions.filter(uuid=version_uuid).first()
        if not version:
            raise CustomError(code=AGENT_VERSION_NOT_FOUND, status_code=404, detail="Version not found.")
        agent.current_version = version
        agent.updated_by = request.user
        agent.system_prompts = version.system_prompts
        agent.llm_configuration = version.llm_configuration
        agent.tools_configuration = version.tools_configuration
        agent.save(update_fields=[
            "current_version",
            "system_prompts",
            "llm_configuration",
            "tools_configuration",
            "updated_by",
            "updated_at",
        ])
        inc_agent_versions_switched()
        return Response(AgentReadSerializer(agent).data, status=status.HTTP_200_OK)

    def _transition(self, agent: Agent, target_state: str):
        valid_transitions = {
            Agent.AgentState.DRAFT: {Agent.AgentState.ACTIVE, Agent.AgentState.DELETED},
            Agent.AgentState.ACTIVE: {Agent.AgentState.ARCHIVED, Agent.AgentState.DELETED},
            Agent.AgentState.ARCHIVED: {Agent.AgentState.ACTIVE, Agent.AgentState.DELETED},
            Agent.AgentState.DELETED: {Agent.AgentState.DRAFT},
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
