# Django import 
from django.utils.translation import gettext_lazy as _

# DRF imports
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response

# Third-party imports
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema

# Local imports
from apps.organizations.models import Organization
from apps.subscriptions.models import (
    Subscription,
)
from apps.subscriptions.serializers import (
    SubscriptionSerializer,
    SubscriptionStatusUpdateSerializer,
)

from apps.roles.permissions import (
    AnyOf,
    IsSaaSAdmin,
    ISSaaSAccountManager,
    IsOrganizationOwner,
    IsOrganizationAdmin,
    IsAccountOwner,
    IsAccountAdmin,
)
@extend_schema(tags=["Subscriptions"])
class SubscriptionViewSet(
    viewsets.mixins.CreateModelMixin,
    viewsets.mixins.ListModelMixin,
    viewsets.mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    ViewSet for managing organization subscriptions.
    - SaaS Admins and Account Managers have full CRUD access.
    - Account Owners and Organization Admins can only list and retrieve subscriptions.
    """
    queryset = Subscription.objects.all()
    serializer_class = SubscriptionSerializer
    filter_backends = [DjangoFilterBackend, ]
    filterset_fields = ["module", "status"]    
    lookup_field = "uuid"

    def get_permissions(self):
        """
        Assigns permissions based on the action.
        - Read actions are allowed for SaaS Admins and Account Managers.
        - Write actions are restricted to SaaS Admins.
        """
        print( self.action )

        if self.action in ["create", "update_status"]:
            return [AnyOf(IsSaaSAdmin, ISSaaSAccountManager)]

        return [
            AnyOf(
                IsSaaSAdmin, ISSaaSAccountManager, IsOrganizationOwner,
                IsOrganizationAdmin, IsAccountOwner, IsAccountAdmin
            )
            ]

    def get_organization(self, organization_uuid):
        try:
            return Organization.objects.get(uuid=organization_uuid)
        except Organization.DoesNotExist:
            err_msg = _("Organization not found")
            raise NotFound(err_msg)

    def get_queryset(self):
        organization_uuid = self.kwargs.get("organization_uuid")

        # Filter users by account_id if provided
        if organization_uuid:
            return self.queryset.filter(
                organization__uuid=organization_uuid
            ).order_by("-created_at")
        return self.queryset.none()

    def perform_create(self, serializer):
        organization_uuid = self.kwargs.get("organization_uuid")
        organization = self.get_organization(organization_uuid)
        serializer.save(
            organization=organization,
            created_by=self.request.user
        )

    @action(
        detail=True,
        methods=["patch"],
        url_path="update-status", 
        serializer_class=SubscriptionStatusUpdateSerializer
    )
    def update_status(self, request, *args, **kwargs):
        """
        Updates the status of a subscription.
        """
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        instance.status = serializer.validated_data['status']
        instance.save()
        return Response(serializer.data)
