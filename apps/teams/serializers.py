from __future__ import annotations

from typing import Any, Dict, Iterable, List

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.common.exceptions import (
    InvalidTeamData,
    TeamNameExists,
    TeamNotFound,
    UserAlreadyMember,
    UserNotMember,
)
from apps.organizations.models import Organization

from .models import Team, TeamMember
from .services import (
    ensure_user_can_create_team,
    ensure_user_can_manage_members,
    ensure_user_can_manage_team,
    ensure_user_can_read_team,
    enforce_team_creation_limits,
    enforce_team_member_limits,
)

User = get_user_model()


class StrictCharField(serializers.CharField):
    """CharField variant that rejects non-string input before coercion."""

    def to_internal_value(self, data: Any) -> str:
        if not isinstance(data, str):
            raise serializers.ValidationError("Must be a string.")
        return super().to_internal_value(data)


class TeamMemberReadSerializer(serializers.ModelSerializer):
    """Read representation of a team membership."""

    user_uuid = serializers.UUIDField(source="user.uuid", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_full_name = serializers.CharField(source="user.full_name", read_only=True)

    class Meta:
        model = TeamMember
        fields = (
            "id",
            "uuid",
            "user",
            "user_uuid",
            "user_email",
            "user_full_name",
            "is_active",
            "assigned_by",
            "assigned_at",
            "role_keys",
        )
        read_only_fields = fields


class TeamReadSerializer(serializers.ModelSerializer):
    """Read representation of a team including members."""

    organization = serializers.IntegerField(source="organization_id", read_only=True)
    member_count = serializers.SerializerMethodField()
    members = serializers.SerializerMethodField()

    class Meta:
        model = Team
        fields = (
            "id",
            "uuid",
            "organization",
            "name",
            "description",
            "configurations",
            "is_active",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
            "deleted_at",
            "member_count",
            "members",
        )
        read_only_fields = fields

    def get_member_count(self, obj: Team) -> int:
        return getattr(obj, "active_member_count", None) or obj.memberships.count()

    def get_members(self, obj: Team) -> List[Dict[str, Any]]:
        memberships = getattr(obj, "_prefetched_memberships", None)
        if memberships is None:
            memberships = obj.memberships.select_related("user", "assigned_by")
        serializer = TeamMemberReadSerializer(memberships, many=True, context=self.context)
        return serializer.data


class TeamCreateSerializer(serializers.ModelSerializer):
    """Serializer used for team creation requests."""

    organization = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all())
    name = StrictCharField(max_length=100)
    description = serializers.CharField(max_length=500, allow_blank=True, required=False)
    configurations = serializers.JSONField(required=False)

    class Meta:
        model = Team
        fields = ("organization", "name", "description", "configurations")

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        request = self.context.get("request")
        request_user = getattr(request, "user", None)
        organization: Organization = attrs["organization"]
        if getattr(organization, "deleted_at", None) is not None or not getattr(organization, "is_active", True):
            raise InvalidTeamData(detail="Organization must be active to create teams.")

        name = attrs.get("name", "").strip()
        attrs["name"] = name
        if Team.objects.filter(organization=organization, name__iexact=name).exists():
            raise TeamNameExists()
        ensure_user_can_create_team(request_user, organization)
        enforce_team_creation_limits(organization=organization)
        return attrs

    def create(self, validated_data: Dict[str, Any]) -> Team:
        request = self.context.get("request")
        request_user = getattr(request, "user", None)
        try:
            instance = Team(**validated_data)
            instance.full_clean()
            instance.created_by = request_user
            instance.updated_by = request_user
            instance.save()
            return instance
        except serializers.ValidationError as exc:
            raise InvalidTeamData(detail="Team model validation failed") from exc


class TeamUpdateSerializer(serializers.ModelSerializer):
    """Serializer handling updates to team metadata."""

    name = StrictCharField(max_length=100, required=False)
    description = serializers.CharField(max_length=500, allow_blank=True, required=False)
    configurations = serializers.JSONField(required=False)
    is_active = serializers.BooleanField(required=False)

    class Meta:
        model = Team
        fields = ("name", "description", "configurations", "is_active")

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        instance: Team = self.instance
        request = self.context.get("request")
        request_user = getattr(request, "user", None)
        ensure_user_can_manage_team(request_user, instance, "teams:update")
        name = attrs.get("name")
        if isinstance(name, str):
            name = name.strip()
            attrs["name"] = name
            if Team.objects.filter(organization=instance.organization, name__iexact=name).exclude(pk=instance.pk).exists():
                raise TeamNameExists()
        return attrs

    def update(self, instance: Team, validated_data: Dict[str, Any]) -> Team:
        for field, value in validated_data.items():
            setattr(instance, field, value)
        try:
            instance.full_clean()
        except serializers.ValidationError as exc:
            raise InvalidTeamData(detail="Team model validation failed") from exc
        request_user = getattr(self.context.get("request"), "user", None)
        instance.updated_by = request_user
        instance.save()
        return instance


class TeamMemberMutationSerializer(serializers.Serializer):
    """Add or reactivate a team membership."""

    user = serializers.UUIDField()
    role_keys = serializers.ListField(
        child=serializers.CharField(max_length=64),
        required=False,
        allow_empty=True,
    )

    def validate_user(self, value):
        try:
            return User.objects.get(uuid=value)
        except User.DoesNotExist as exc:
            raise InvalidTeamData(detail="User does not exist.") from exc

    def validate_role_keys(self, value: Iterable[str]):
        cleaned: List[str] = []
        for item in value or []:
            if not isinstance(item, str) or not item.strip():
                raise InvalidTeamData(detail="Role keys must be non-empty strings.")
            cleaned.append(item.strip())
        return cleaned

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        request = self.context.get("request")
        team: Team = self.context["team"]
        request_user = getattr(request, "user", None)
        user: User = attrs["user"]
        if not getattr(user, "is_active", False):
            raise InvalidTeamData(detail="Target user must be active.")
        ensure_user_can_manage_members(request_user, team)
        if TeamMember.objects.filter(team=team, user=user, deleted_at__isnull=True).exists():
            raise UserAlreadyMember()
        enforce_team_member_limits(team=team)
        attrs["user"] = user
        return attrs

    @transaction.atomic
    def save(self) -> TeamMember:
        team: Team = self.context["team"]
        request = self.context.get("request")
        request_user = getattr(request, "user", None)
        user: User = self.validated_data["user"]
        role_keys: List[str] = self.validated_data.get("role_keys", [])
        existing = TeamMember.all_objects.filter(team=team, user=user).order_by("-created_at").first()
        if existing and existing.deleted_at is not None:
            existing.deleted_at = None
            existing.is_active = True
            existing.role_keys = role_keys
            existing.assigned_by = request_user
            existing.full_clean()
            existing.save(update_fields=[
                "deleted_at",
                "is_active",
                "role_keys",
                "assigned_by",
                "updated_at",
            ])
            return existing
        membership = TeamMember(team=team, user=user, assigned_by=request_user, role_keys=role_keys)
        membership.full_clean()
        membership.save()
        return membership


class TeamMemberRemovalSerializer(serializers.Serializer):
    """Remove a user from a team."""

    user = serializers.UUIDField()

    def validate_user(self, value):
        try:
            return User.objects.get(uuid=value)
        except User.DoesNotExist as exc:
            raise UserNotMember() from exc

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        request = self.context.get("request")
        team: Team = self.context["team"]
        request_user = getattr(request, "user", None)
        user: User = attrs["user"]
        ensure_user_can_manage_members(request_user, team)
        try:
            membership = TeamMember.objects.get(team=team, user=user)
        except TeamMember.DoesNotExist as exc:
            raise UserNotMember() from exc
        attrs["membership"] = membership
        return attrs

    @transaction.atomic
    def remove(self) -> None:
        membership: TeamMember = self.validated_data["membership"]
        membership.delete()


__all__ = [
    "TeamCreateSerializer",
    "TeamUpdateSerializer",
    "TeamReadSerializer",
    "TeamMemberMutationSerializer",
    "TeamMemberRemovalSerializer",
    "TeamMemberReadSerializer",
]
