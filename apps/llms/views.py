from __future__ import annotations

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.agents.definitions import get_llm_definition, list_llm_definitions
from apps.agents.models import OrganizationEnabledLLM
from apps.llms.serializers import (
    LLMDefinitionSerializer,
    LLMValidationSerializer,
    OrganizationEnabledLLMSerializer,
)
from apps.llms.services import (
    disable_llm,
    enable_llm,
    ensure_llm_permission,
    validate_configuration,
)
from apps.organizations.models import Organization


class LLMDefinitionListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=LLMDefinitionSerializer(many=True))
    def get(self, request):
        definitions = list_llm_definitions()
        payload = []
        for definition in definitions:
            payload.append(
                {
                    "modelKey": definition.key,
                    "modelProvider": definition.provider,
                    "displayName": definition.display_name,
                    "description": definition.description,
                    "maxContextTokens": definition.raw.get("maxContextTokens"),
                    "supportedModalities": definition.raw.get("supportedModalities", []),
                }
            )
        serializer = LLMDefinitionSerializer(payload, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class LLMDefinitionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=LLMDefinitionSerializer)
    def get(self, request, model_key: str):
        definition = get_llm_definition(model_key)
        if not definition:
            return Response({"code": "LLM_NOT_FOUND", "message": "Unknown LLM key."}, status=status.HTTP_404_NOT_FOUND)
        data = {
            "modelKey": definition.key,
            "modelProvider": definition.provider,
            "displayName": definition.display_name,
            "description": definition.description,
            "maxContextTokens": definition.raw.get("maxContextTokens"),
            "supportedModalities": definition.raw.get("supportedModalities", []),
        }
        serializer = LLMDefinitionSerializer(data)
        return Response(serializer.data, status=status.HTTP_200_OK)


class LLMDefinitionSchemaView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, model_key: str):
        definition = get_llm_definition(model_key)
        if not definition:
            return Response({"code": "LLM_NOT_FOUND", "message": "Unknown LLM key."}, status=status.HTTP_404_NOT_FOUND)
        schema = definition.raw.get("modelConfiguration") or {}
        return Response(schema, status=status.HTTP_200_OK)


class LLMValidationView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=LLMValidationSerializer, responses=LLMValidationSerializer)
    def post(self, request):
        serializer = LLMValidationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = get_object_or_404(Organization, uuid=serializer.validated_data["organization_uuid"])
        ensure_llm_permission(request.user, organization, "llms:read")
        validated = validate_configuration(serializer.validated_data, organization=organization)
        return Response(validated, status=status.HTTP_200_OK)


class OrganizationLLMViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = OrganizationEnabledLLMSerializer

    def _organization(self):
        if not hasattr(self, "_cached_org"):
            self._cached_org = get_object_or_404(Organization, uuid=self.kwargs["organization_uuid"])
        return self._cached_org

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return OrganizationEnabledLLM.objects.none()
        organization = self._organization()
        ensure_llm_permission(self.request.user, organization, "llms:read")
        return OrganizationEnabledLLM.objects.filter(organization=organization, disabled_at__isnull=True)


class OrganizationLLMEnableView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, organization_uuid: str, model_key: str):
        organization = get_object_or_404(Organization, uuid=organization_uuid)
        ensure_llm_permission(request.user, organization, "llms:enable")
        record = enable_llm(organization, model_key, request.user)
        serializer = OrganizationEnabledLLMSerializer(record)
        return Response(serializer.data, status=status.HTTP_200_OK)


class OrganizationLLMDisableView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, organization_uuid: str, model_key: str):
        organization = get_object_or_404(Organization, uuid=organization_uuid)
        ensure_llm_permission(request.user, organization, "llms:disable")
        record = disable_llm(organization, model_key, request.user)
        serializer = OrganizationEnabledLLMSerializer(record)
        return Response(serializer.data, status=status.HTTP_200_OK)
