# Django imports
from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _

# Third-party imports
# from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from rest_framework import mixins, viewsets
from rest_framework.exceptions import ValidationError, PermissionDenied

# Local imports
from apps.roles.models import Role
from apps.roles.models import RoleAssignment
from apps.roles.constants import ROLE_ORGANIZATION_OWNER
from apps.organizations.models import Organization

from apps.roles.serializers import RoleSerializer
from apps.roles.serializers import RoleAssignmentSerializer

from apps.roles.permissions import IsOrganizationAdmin

from apps.common.exceptions import OrganizationNotFound

# @extend_schema(tags=["Roles"])
@extend_schema(
    tags=["Roles"],
    parameters=[
        OpenApiParameter(
            name='organization_uuid',
            description='UUID of the organization',
            required=True,
            type=OpenApiTypes.UUID,  # Or STRING if it's not a UUID
            location=OpenApiParameter.PATH,
        ),
    ]
)
class RoleViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing Roles within an organization.
    - Create Custom Role
    - Retrieve Role Information
    - Update Custom Role
    - Delete Custom Role
    - List Roles with Pagination
    """

    serializer_class = RoleSerializer
    queryset = Role.objects.all()
    lookup_field = "uuid"
    permission_classes = [IsOrganizationAdmin]

    def get_queryset(self):
        """
        Filter roles to the organization specified in the URL.
        """
        organization_uuid = self.kwargs.get("organization_uuid")
        # TODO: Add permission check to ensure user is part of this organization.
        return self.queryset.filter(organization__uuid=organization_uuid)

    def perform_create(self, serializer):
        """
        Create a new custom role for an organization.
        """
        try:
            organization = Organization.objects.get(uuid=self.kwargs["organization_uuid"])

            # Check organization role limits
            if organization.roles.count() >= 100:
                err_msg = _(
                    "The organization has reached the maximum number of roles (100)."
                )
                raise ValidationError(err_msg)

            serializer.save(
                organization=organization,
                created_by=self.request.user,
                role_type=Role.RoleType.USER_CUSTOM,
            )
        except Organization.DoesNotExist:
            raise OrganizationNotFound()

        except IntegrityError:
            # Handles the model's UniqueConstraint for name+organization
            raise ValidationError(
                {
                    "name": _("A role with this name already exists in the organization.")
                }
            )

    def perform_update(self, serializer):
        """
        Update a custom role.
        """
        role = self.get_object()
        if role.role_type != Role.RoleType.USER_CUSTOM:
            raise PermissionDenied(_("Cannot update a system or predefined role."))
        serializer.save()

    def perform_destroy(self, instance):
        """
        Soft-delete a custom role.
        """
        if instance.role_type != Role.RoleType.USER_CUSTOM:
            raise PermissionDenied(_("Cannot delete a system or predefined role."))

        if instance.assignments.exists():
            raise ValidationError(
                _("Cannot delete a role that is currently assigned to one or more users.")
            )

        instance.delete()  # Uses the model's soft-delete method


@extend_schema(tags=["Role Assignments"])

class RoleAssignmentViewSet(
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Manage role assignments within an organization."""

    serializer_class = RoleAssignmentSerializer
    queryset = RoleAssignment.objects.all()
    lookup_field = "uuid"
    permission_classes = [IsOrganizationAdmin]

    def _get_organization(self):
        if not hasattr(self, "_organization_cache"):
            organization_uuid = self.kwargs.get("organization_uuid")
            if not organization_uuid:
                raise ValidationError(_("Organization identifier is required."))
            self._organization_cache = get_object_or_404(
                Organization,
                uuid=organization_uuid,
            )
        return self._organization_cache

    def get_queryset(self):
        organization = self._get_organization()
        return (
            self.queryset.filter(organization=organization)
            .select_related("user", "role")
            .order_by("-created_at")
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["organization"] = self._get_organization()
        return context

    def perform_create(self, serializer):
        organization = self._get_organization()
        try:
            serializer.save(
                organization=organization,
                assigned_by=self.request.user,
            )
        except IntegrityError as exc:
            raise ValidationError(
                {"role": _("User already has this role.")}
            ) from exc

    def perform_destroy(self, instance):
        if instance.role.role_type in [Role.RoleType.SYSTEM, Role.RoleType.USER]:
            raise PermissionDenied(
                _("Cannot modify assignments for system-managed roles."),
            )

        if (
            instance.organization_id
            and instance.role.name == ROLE_ORGANIZATION_OWNER
        ):
            remaining_owner_exists = RoleAssignment.objects.filter(
                organization_id=instance.organization_id,
                role__name=ROLE_ORGANIZATION_OWNER,
                is_active=True,
            ).exclude(pk=instance.pk).exists()
            if not remaining_owner_exists:
                raise ValidationError(
                    _("Organization must retain at least one owner."),
                )

        instance.delete()
