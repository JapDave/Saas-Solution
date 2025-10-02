from django.db import IntegrityError
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError, PermissionDenied

from apps.roles.models import Role, RoleAssignment
from apps.roles.serializers import RoleSerializer, RoleAssignmentSerializer
from apps.organizations.models import Organization
from apps.roles.permissions import IsSaaSAdmin



@extend_schema(tags=["Roles"])
class RoleViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing Roles within an organization.
    - REQ-ROLE-001: Create Custom Role
    - REQ-ROLE-002: Retrieve Role Information
    - REQ-ROLE-003: Update Custom Role
    - REQ-ROLE-004: Delete Custom Role
    - REQ-ROLE-007: List Roles with Pagination
    """

    serializer_class = RoleSerializer
    queryset = Role.objects.all()
    lookup_field = "uuid"
    permission_class = [IsSaaSAdmin]

    def get_queryset(self):
        """
        Filter roles to the organization specified in the URL.
        """
        organization_uuid = self.kwargs.get("organization_uuid")
        # TODO: Add permission check to ensure user is part of this organization.
        return self.queryset.filter(organization__uuid=organization_uuid)

    def perform_create(self, serializer):
        """
        REQ-ROLE-001: Create a new custom role for an organization.
        """
        organization = Organization.objects.get(uuid=self.kwargs["organization_uuid"])

        # REQ-ROLE-001: Check organization role limits
        if organization.roles.count() >= 100:
            raise ValidationError(_("Organization has reached the maximum limit of 100 custom roles."))

        try:
            serializer.save(
                organization=organization,
                created_by=self.request.user,
                role_type=Role.RoleType.USER_CUSTOM,
            )
        except IntegrityError:
            # Handles the model's UniqueConstraint for name+organization
            raise ValidationError({"name": _("A role with this name already exists in the organization.")})

    def perform_update(self, serializer):
        """
        REQ-ROLE-003: Update a custom role.
        """
        role = self.get_object()
        if role.role_type != Role.RoleType.USER_CUSTOM:
            raise PermissionDenied(_("Cannot update a system or predefined role."))
        serializer.save()

    def perform_destroy(self, instance):
        """
        REQ-ROLE-004: Soft-delete a custom role.
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
    viewsets.mixins.CreateModelMixin,
    viewsets.mixins.DestroyModelMixin,
    viewsets.mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """
    API endpoint for assigning and removing roles from users.
    - REQ-ROLE-005: Assign Role to User
    - REQ-ROLE-006: Remove Role from User
    """

    serializer_class = RoleAssignmentSerializer
    queryset = RoleAssignment.objects.all()
    lookup_field = "uuid"

    def get_queryset(self):
        """
        Filter assignments to the organization specified in the URL.
        """
        organization_uuid = self.kwargs.get("organization_uuid")
        # TODO: Add permission check to ensure user is part of this organization.
        return self.queryset.filter(organization__uuid=organization_uuid)

    def perform_create(self, serializer):
        """
        REQ-ROLE-005: Assign a role to a user within the organization.
        """
        organization = Organization.objects.get(uuid=self.kwargs["organization_uuid"])

        # TODO: REQ-ROLE-005: Validate target user is member of organization.
        # This would typically involve checking a membership model, e.g.,
        # if not OrganizationMember.objects.filter(user=user, organization=organization).exists():
        #     raise ValidationError(...)

        try:
            serializer.save(
                organization=organization,
                assigned_by=self.request.user,
            )
        except IntegrityError:
            # Handles the model's UniqueConstraint for user+role+organization
            raise ValidationError(_("This user is already assigned this role in the organization."))

    def perform_destroy(self, instance):
        """
        REQ-ROLE-006: Remove a role assignment from a user (soft delete).
        """
        # TODO: REQ-ROLE-006: Add authority validation. A user should not be able
        # to remove the last 'Organization Owner' role, for example.
        if instance.role.role_type in [Role.RoleType.SYSTEM, Role.RoleType.USER]:
            raise PermissionDenied(_("Cannot remove an assignment for a system-managed role."))

        instance.delete()
