# Django import 
from django.utils.translation import gettext_lazy as _

# DRF imports
from rest_framework import viewsets
from rest_framework.exceptions import NotFound

# Third-party imports
from drf_spectacular.utils import extend_schema

# Local imports
from apps.organizations.models import Organization
from apps.subscriptions.models import (
    Subscription,
)
from apps.subscriptions.serializers import (
    SubscriptionSerializer,
)


@extend_schema(tags=["Subscriptions"])
class SubscriptionViewSet(viewsets.ModelViewSet):
    queryset = Subscription.objects.all()
    serializer_class = SubscriptionSerializer
    lookup_field = "uuid"

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
