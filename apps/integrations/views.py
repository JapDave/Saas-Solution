from __future__ import annotations

from collections import Counter

from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import CustomError, INTEGRATION_DELETED, INTEGRATION_NOT_FOUND
from apps.integrations.models import Integration
from apps.integrations.serializers import (
    IntegrationAnalyticsSerializer,
    IntegrationReadSerializer,
    IntegrationTypeSerializer,
    IntegrationWriteSerializer,
    IntegrationTestSerializer,
    integration_type_payload,
)
from apps.integrations.services import (
    ensure_integration_permission,
    enforce_integration_limit,
    regenerate_webhook_secret,
    resolve_integration_limits,
)
from apps.integrations.testing import run_mock_integration_test
from apps.organizations.models import Organization


class IntegrationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    lookup_field = "uuid"

    def _organization(self) -> Organization:
        if not hasattr(self, "_cached_org"):
            self._cached_org = get_object_or_404(Organization, uuid=self.kwargs["organization_uuid"])
        return self._cached_org

    def get_queryset(self):
        organization = self._organization()
        include_deleted = self.request.query_params.get("includeDeleted") == "true"
        base = Integration.all_objects if include_deleted else Integration.objects
        queryset = base.filter(organization=organization)
        integration_type = self.request.query_params.get("integration_type")
        if integration_type:
            queryset = queryset.filter(integration_type=integration_type)
        state = self.request.query_params.get("state")
        if state:
            queryset = queryset.filter(state=state)
        return queryset.order_by("name")

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return IntegrationWriteSerializer
        return IntegrationReadSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["organization"] = self._organization()
        return context

    def list(self, request, *args, **kwargs):
        ensure_integration_permission(request.user, self._organization(), "integrations:read")
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        ensure_integration_permission(request.user, self._organization(), "integrations:read")
        return super().retrieve(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        organization = self._organization()
        ensure_integration_permission(request.user, organization, "integrations:create")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        integration = serializer.save()
        read = IntegrationReadSerializer(
            integration,
            context={"include_secret": integration.integration_type == Integration.IntegrationType.WEBHOOK},
        )
        headers = self.get_success_headers(read.data)
        return Response(read.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        organization = self._organization()
        ensure_integration_permission(request.user, organization, "integrations:update")
        kwargs["partial"] = kwargs.pop("partial", False)
        instance = self.get_object()
        if instance.state == Integration.IntegrationState.DELETED:
            raise CustomError(code=INTEGRATION_DELETED, status_code=400, detail="Integration is deleted.")
        serializer = self.get_serializer(instance, data=request.data, partial=kwargs["partial"])
        serializer.is_valid(raise_exception=True)
        integration = serializer.save()
        read = IntegrationReadSerializer(integration)
        return Response(read.data)

    def perform_destroy(self, instance):
        ensure_integration_permission(self.request.user, instance.organization, "integrations:delete")
        instance.mark_deleted()

    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, *args, **kwargs):
        integration = self.get_object()
        ensure_integration_permission(request.user, integration.organization, "integrations:activate")
        if integration.state == Integration.IntegrationState.DELETED:
            raise CustomError(code=INTEGRATION_DELETED, status_code=400, detail="Integration is deleted.")
        integration.state = Integration.IntegrationState.ACTIVE
        integration.is_active = True
        integration.save(update_fields=["state", "is_active", "updated_at"])
        return Response(IntegrationReadSerializer(integration).data)

    @action(detail=True, methods=["post"], url_path="deactivate")
    def deactivate(self, request, *args, **kwargs):
        integration = self.get_object()
        ensure_integration_permission(request.user, integration.organization, "integrations:deactivate")
        if integration.state == Integration.IntegrationState.DELETED:
            raise CustomError(code=INTEGRATION_DELETED, status_code=400, detail="Integration is deleted.")
        integration.state = Integration.IntegrationState.INACTIVE
        integration.is_active = False
        integration.save(update_fields=["state", "is_active", "updated_at"])
        return Response(IntegrationReadSerializer(integration).data)

    @action(detail=True, methods=["post"], url_path="regenerate-secret")
    def regenerate_secret(self, request, *args, **kwargs):
        integration = self.get_object()
        ensure_integration_permission(request.user, integration.organization, "integrations:regenerate_secret")
        secret = regenerate_webhook_secret(integration)
        payload = IntegrationReadSerializer(
            integration,
            context={"include_secret": True},
        ).data
        payload["webhook_secret"] = secret
        return Response(payload, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="test")
    def test_integration(self, request, *args, **kwargs):
        integration = self.get_object()
        ensure_integration_permission(request.user, integration.organization, "integrations:test")
        serializer = IntegrationTestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = run_mock_integration_test(integration, serializer.validated_data.get("parameters"))
        return Response(result, status=status.HTTP_200_OK)


class IntegrationAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, organization_uuid: str):
        organization = get_object_or_404(Organization, uuid=organization_uuid)
        ensure_integration_permission(request.user, organization, "integrations:read")
        qs = Integration.all_objects.filter(organization=organization)
        stats: dict[str, Counter] = {"api": Counter(), "webhook": Counter()}
        totals = {"api": {"month": 0, "total": 0}, "webhook": {"month": 0, "total": 0}}
        for integration in qs:
            stats[integration.integration_type][integration.state] += 1
            totals[integration.integration_type]["month"] += integration.invocation_count_month
            totals[integration.integration_type]["total"] += integration.invocation_count_total
        payload = []
        for integration_type, counts in stats.items():
            payload.append(
                {
                    "integration_type": integration_type,
                    "active": counts.get(Integration.IntegrationState.ACTIVE, 0),
                    "inactive": counts.get(Integration.IntegrationState.INACTIVE, 0),
                    "deleted": counts.get(Integration.IntegrationState.DELETED, 0),
                    "invocation_count_month": totals[integration_type]["month"],
                    "invocation_count_total": totals[integration_type]["total"],
                }
            )
        serializer = IntegrationAnalyticsSerializer(payload, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class IntegrationTypesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, organization_uuid: str):
        organization = get_object_or_404(Organization, uuid=organization_uuid)
        ensure_integration_permission(request.user, organization, "integrations:read")
        payload = integration_type_payload(organization)
        serializer = IntegrationTypeSerializer(
            [
                {
                    "integration_type": entry["integrationType"],
                    "enabled": entry["enabled"],
                    "max_instances": entry["maxInstances"],
                    "max_invocations": entry["maxInvocationsPerMonth"],
                }
                for entry in payload
            ],
            many=True,
        )
        return Response(serializer.data, status=status.HTTP_200_OK)


class IntegrationAnalyticsDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, organization_uuid: str, integration_uuid: str):
        organization = get_object_or_404(Organization, uuid=organization_uuid)
        integration = get_object_or_404(
            Integration.all_objects.filter(organization=organization),
            uuid=integration_uuid,
        )
        ensure_integration_permission(request.user, organization, "integrations:read")
        data = {
            "integration_type": integration.integration_type,
            "active": 1 if integration.state == Integration.IntegrationState.ACTIVE else 0,
            "inactive": 1 if integration.state == Integration.IntegrationState.INACTIVE else 0,
            "deleted": 1 if integration.state == Integration.IntegrationState.DELETED else 0,
            "invocation_count_month": integration.invocation_count_month,
            "invocation_count_total": integration.invocation_count_total,
        }
        serializer = IntegrationAnalyticsSerializer(data)
        return Response(serializer.data, status=status.HTTP_200_OK)
