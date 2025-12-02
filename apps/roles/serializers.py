from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from apps.common.exceptions import CustomError, ROLE_NAME_CONFLICT

from apps.roles.models import Role, RoleAssignment
from apps.users.models import User, UserOrganization


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
        Validate permission limits and normalise keys.
        """
        if not isinstance(permissions, (list, tuple)):
            raise serializers.ValidationError(
                {"permissions": _("Permissions must be provided as a list of strings.")}
            )
        if len(permissions) > 200:
            raise serializers.ValidationError(
                {"permissions": _("A role cannot have more than 200 permissions.")}
            )

        normalised = []
        seen = set()
        for perm in permissions:
            if not isinstance(perm, str):
                raise serializers.ValidationError(
                    {"permissions": _("Each permission must be a string key.")}
                )
            value = perm.strip().lower()
            if not value:
                raise serializers.ValidationError(
                    {"permissions": _("Permission keys cannot be blank.")}
                )
            if ":" not in value:
                raise serializers.ValidationError(
                    {
                        "permissions": _(
                            "Permission keys must use the 'scope:action' format."
                        )
                    }
                )
            if value not in seen:
                seen.add(value)
                normalised.append(value)

        normalised.sort()
        return normalised

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
                raise CustomError(
                    code=ROLE_NAME_CONFLICT,
                    status_code=409,
                    detail=str(
                        _("A role with this name already exists in the organization.")
                    ),
                )
        return data


class RoleAssignmentSerializer(serializers.ModelSerializer):
    """
    Serializer for the RoleAssignment model.
    """

    user = serializers.SlugRelatedField(
        slug_field="uuid",
        queryset=User.objects.all(),
        required=True,
    )
    role = serializers.SlugRelatedField(
        slug_field="uuid",
        queryset=Role.objects.all(),
        required=True,
    )
    organization = serializers.UUIDField(read_only=True, source="organization.uuid")

    class Meta:
        model = RoleAssignment
        fields = [
            "uuid",
            "user",
            "role",
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

    def validate(self, attrs):
        organization = self.context.get("organization")
        if organization is None:
            raise serializers.ValidationError("Organization context is required.")

        user: User = attrs.get("user")
        role: Role = attrs.get("role")

        if user is None or role is None:
            return attrs

        if role.organization_id != organization.id:
            raise serializers.ValidationError(
                {"role": _("Role must belong to the organization.")}
            )

        if not role.is_active:
            raise serializers.ValidationError({"role": _("Role is inactive.")})

        membership_exists = UserOrganization.objects.filter(
            user=user,
            organization=organization,
            is_active=True,
            deleted_at__isnull=True,
        ).exists()
        if not membership_exists:
            raise serializers.ValidationError(
                {"user": _("User must be an active member of the organization.")}
            )

        attrs["organization"] = organization
        return attrs

    def create(self, validated_data):
        organization = validated_data.pop("organization")
        assigned_by = validated_data.pop("assigned_by", None)
        user: User = validated_data["user"]
        role: Role = validated_data["role"]

        existing = RoleAssignment.objects.filter(
            user=user,
            role=role,
            organization=organization,
        ).first()
        if existing:
            raise serializers.ValidationError(
                {"role": _("User already has this role.")}
            )

        archived = (
            RoleAssignment.all_objects.filter(
                user=user,
                role=role,
                organization=organization,
            )
            .exclude(deleted_at__isnull=True)
            .first()
        )
        if archived:
            archived.deleted_at = None
            archived.is_active = True
            archived.assigned_by = assigned_by
            archived.save(
                update_fields=["deleted_at", "is_active", "assigned_by", "updated_at"]
            )
            return archived

        return RoleAssignment.objects.create(
            organization=organization,
            assigned_by=assigned_by,
            **validated_data,
        )
