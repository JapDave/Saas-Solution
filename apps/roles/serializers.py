from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.roles.models import Role, RoleAssignment


class RoleSerializer(serializers.ModelSerializer):
    """
    Serializer for the Role model. Handles creation, updates, and retrieval of roles.
    """

    class Meta:
        model = Role
        fields = [
            "uuid",
            "organization",
            "name",
            "description",
            "permissions",
            "role_type",
            "is_active",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "uuid",
            "organization",
            "role_type",
            "created_at",
            "updated_at",
        ]

    def validate_permissions(self, permissions):
        """
        REQ-ROLE-001: Validate all permissions are available through subscriptions.
        Placeholder for subscription-based permission validation.
        """
        if len(permissions) > 200:
            raise serializers.ValidationError(
                _("A role cannot have more than 200 permissions.")
            )
        # TODO: Implement logic to check if the organization's subscription
        # allows for the given permissions.
        return permissions

    def validate(self, data):
        """
        On update, ensure the role name remains unique within the organization.
        """
        if self.instance:  # This is an update
            name = data.get("name", self.instance.name)
            organization = self.instance.organization
            if (
                Role.objects.filter(organization=organization, name=name)
                .exclude(pk=self.instance.pk)
                .exists()
            ):
                raise serializers.ValidationError(
                    {"name": _("A role with this name already exists in the organization.")}
                )
        return data


class RoleAssignmentSerializer(serializers.ModelSerializer):
    """
    Serializer for the RoleAssignment model.
    """

    user_id = serializers.UUIDField(write_only=True, source="user")
    role_id = serializers.UUIDField(source="role")

    class Meta:
        model = RoleAssignment
        fields = [
            "uuid",
            "user",
            "user_id",
            "role",
            "role_id",
            "organization",
            "assigned_by",
            "assigned_at",
            "created_at",
        ]
        read_only_fields = [
            "uuid",
            "organization",
            "assigned_by",
            "assigned_at",
            "created_at",
        ]
        # The unique_together constraint on the model handles duplicate assignments.
