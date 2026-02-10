from __future__ import annotations

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.agents.definitions import get_llm_definition, list_llm_definitions
from apps.agents.models import OrganizationEnabledLLM, Agent
from apps.llms.serializers import (
    LLMDefinitionSerializer,
    LLMValidationSerializer,
)
from apps.llms.services import (
    disable_llm,
    enable_llm,
    ensure_llm_permission,
    ensure_llm_subscription,
    validate_configuration,
    agents_usage_by_model_keys,
)
from apps.llms.telemetry import inc_llm_list, inc_llm_validation, inc_llm_schema
from apps.organizations.models import Organization
from apps.agents.services import ensure_llm_allowed_for_subscription


class OrganizationLLMDefinitionsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=LLMDefinitionSerializer(many=True))
    def get(self, request, organization_uuid: str):
        organization = get_object_or_404(Organization, uuid=organization_uuid)
        ensure_llm_subscription(organization)
        ensure_llm_permission(request.user, organization, "llms:list")
        inc_llm_list()
        inc_llm_schema()

        provider_filter = (request.query_params.get("provider") or "").strip().lower()
        modality_filter = (request.query_params.get("modality") or "").strip().lower()

        definitions = list_llm_definitions()
        # filter hosted models by subscription allowance
        filtered_defs = []
        for definition in definitions:
            if provider_filter and definition.provider.lower() != provider_filter:
                continue
            if modality_filter and modality_filter not in [
                (m or "").strip().lower() for m in (definition.raw.get("supportedModalities") or [])
            ]:
                continue
            try:
                ensure_llm_allowed_for_subscription(organization, definition.key)
            except Exception:
                # skip hosted models not permitted
                continue
            filtered_defs.append(definition)

        usage = agents_usage_by_model_keys(organization, [d.key for d in filtered_defs])
        payload = []
        for definition in filtered_defs:
            payload.append(
                {
                    "modelKey": definition.key,
                    "modelProvider": definition.provider,
                    "displayName": definition.display_name,
                    "description": definition.description,
                    "maxContextTokens": definition.raw.get("maxContextTokens"),
                    "supportedModalities": definition.raw.get("supportedModalities", []),
                    "modelConfiguration": definition.raw.get("modelConfiguration") or {},
                    "usedByAgents": usage.get(definition.key, 0),
                }
            )
        serializer = LLMDefinitionSerializer(payload, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class LLMValidationView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=LLMValidationSerializer, responses=LLMValidationSerializer)
    def post(self, request):
        serializer = LLMValidationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = get_object_or_404(Organization, uuid=serializer.validated_data["organization_uuid"])
        ensure_llm_subscription(organization)
        ensure_llm_permission(request.user, organization, "llms:read")
        try:
            validated = validate_configuration(serializer.validated_data, organization=organization)
            inc_llm_validation(success=True)
            return Response(validated, status=status.HTTP_200_OK)
        except Exception:
            inc_llm_validation(success=False)
            raise


class OrganizationLLMViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = LLMDefinitionSerializer

    def _organization(self):
        if not hasattr(self, "_cached_org"):
            self._cached_org = get_object_or_404(Organization, uuid=self.kwargs["organization_uuid"])
        return self._cached_org

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return OrganizationEnabledLLM.objects.none()
        organization = self._organization()
        ensure_llm_subscription(organization)
        ensure_llm_permission(self.request.user, organization, "llms:read")
        return OrganizationEnabledLLM.objects.filter(organization=organization, disabled_at__isnull=True)

    @extend_schema(responses=LLMDefinitionSerializer(many=True))
    def list(self, request, *args, **kwargs):
        organization = self._organization()
        ensure_llm_subscription(organization)
        ensure_llm_permission(request.user, organization, "llms:read")
        inc_llm_list()
        enabled = list(self.get_queryset())
        model_keys = [row.model_key for row in enabled]
        usage = agents_usage_by_model_keys(organization, model_keys)
        definitions = {d.key: d for d in list_llm_definitions()}

        payload = []
        for row in enabled:
            definition = definitions.get(row.model_key)
            if not definition:
                continue
            payload.append(
                {
                    "modelKey": definition.key,
                    "modelProvider": definition.provider,
                    "displayName": definition.display_name,
                    "description": definition.description,
                    "maxContextTokens": definition.raw.get("maxContextTokens"),
                    "supportedModalities": definition.raw.get("supportedModalities", []),
                    "modelConfiguration": definition.raw.get("modelConfiguration") or {},
                    "usedByAgents": usage.get(definition.key, 0),
                }
            )
        serializer = LLMDefinitionSerializer(payload, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class OrganizationLLMEnableView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses=LLMDefinitionSerializer)
    def post(self, request, organization_uuid: str, model_key: str):
        organization = get_object_or_404(Organization, uuid=organization_uuid)
        ensure_llm_subscription(organization)
        ensure_llm_permission(request.user, organization, "llms:enable")
        record = enable_llm(organization, model_key, request.user)
        usage = agents_usage_by_model_keys(organization, [record.model_key]).get(record.model_key, 0)
        definition = get_llm_definition(record.model_key)
        payload = {
            "modelKey": record.model_key,
            "modelProvider": record.model_provider,
            "displayName": definition.display_name if definition else record.model_key,
            "description": definition.description if definition else "",
            "modelConfiguration": definition.raw.get("modelConfiguration") if definition else {},
            "usedByAgents": usage,
        }
        serializer = LLMDefinitionSerializer(payload)
        return Response(serializer.data, status=status.HTTP_200_OK)


class OrganizationLLMDisableView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses=LLMDefinitionSerializer)
    def post(self, request, organization_uuid: str, model_key: str):
        organization = get_object_or_404(Organization, uuid=organization_uuid)
        ensure_llm_subscription(organization)
        ensure_llm_permission(request.user, organization, "llms:disable")
        record = disable_llm(organization, model_key, request.user)
        usage = agents_usage_by_model_keys(organization, [record.model_key]).get(record.model_key, 0)
        definition = get_llm_definition(record.model_key)
        warning = None
        if usage > 0:
            warning = f"{usage} agent(s) currently use this LLM. Disabling will hide it from new configs."
        payload = {
            "modelKey": record.model_key,
            "modelProvider": record.model_provider,
            "displayName": definition.display_name if definition else record.model_key,
            "description": definition.description if definition else "",
            "modelConfiguration": definition.raw.get("modelConfiguration") if definition else {},
            "usedByAgents": usage,
            "disabledAt": record.disabled_at,
            "warning": warning,
        }
        serializer = LLMDefinitionSerializer(payload)
        status_code = status.HTTP_200_OK
        return Response(serializer.data, status=status_code)
