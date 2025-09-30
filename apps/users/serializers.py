from __future__ import annotations

from typing import Any, Dict, Iterable, List

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers

from apps.common.exceptions import (
    EmailAlreadyExists,
    InvalidUserData,
    UserAlreadyMember,
    UserNotMember,
)
from apps.organizations.models import Organization

from .models import UserOrganization
from .services import assert_actor_can_manage_organization

User = get_user_model()


class MembershipSerializer(serializers.ModelSerializer):
    organization_uuid = serializers.UUIDField(source="organization.uuid", read_only=True)
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    account_id = serializers.IntegerField(source="organization.account_id", read_only=True)
    account_uuid = serializers.UUIDField(source="organization.account.uuid", read_only=True)
    permissions = serializers.ListField(child=serializers.CharField(), source="permission_keys", read_only=True)

    class Meta:
        model = UserOrganization
        fields = (
            "id",
            "uuid",
            "organization",
            "organization_uuid",
            "organization_name",
            "account_id",
            "account_uuid",
            "permissions",
            "is_active",
            "assigned_by",
            "assigned_at",
            "created_at",
            "updated_at",
            "deleted_at",
        )
        read_only_fields = fields


class MembershipInputSerializer(serializers.Serializer):
    organization = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all())
    permissions = serializers.ListField(child=serializers.CharField(), allow_empty=True, required=False)

    def validate_permissions(self, permissions: Iterable[str]):
        cleaned = []
        for perm in permissions or []:
            if not isinstance(perm, str) or not perm.strip():
                raise serializers.ValidationError("Each permission must be a non-empty string.")
            cleaned.append(perm.strip())
        return cleaned


class UserReadSerializer(serializers.ModelSerializer):
    memberships = MembershipSerializer(many=True, read_only=True, source="memberships")

    class Meta:
        model = User
        fields = (
            "id",
            "uuid",
            "email",
            "full_name",
            "profile_image",
            "user_preferences",
            "is_active",
            "is_staff",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
            "deleted_at",
            "memberships",
        )
        read_only_fields = fields


class UserCreateSerializer(serializers.ModelSerializer):
    memberships = MembershipInputSerializer(many=True)
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = (
            "email",
            "password",
            "full_name",
            "profile_image",
            "user_preferences",
            "memberships",
        )

    def validate_email(self, value: str) -> str:
        if User.objects.with_deleted().filter(email__iexact=value).exists():
            raise EmailAlreadyExists()
        return value

    def validate_password(self, value: str) -> str:
        if not isinstance(value, str) or not 8 <= len(value) <= 128:
            raise InvalidUserData(detail="Password must be between 8 and 128 characters.")
        return value

    def validate_memberships(self, value: List[Dict[str, Any]]):
        if not value:
            raise InvalidUserData(detail="User must be assigned to at least one organization.")
        request = self.context.get("request")
        actor = getattr(request, "user", None)
        if actor is None:
            raise InvalidUserData(detail="Actor context required.")
        seen_orgs = set()
        for item in value:
            organization = item.get("organization")
            if organization is None:
                raise InvalidUserData(detail="Organization membership entry is missing organization reference.")
            if organization.id in seen_orgs:
                raise InvalidUserData(detail="Duplicate organization entries are not allowed.")
            seen_orgs.add(organization.id)
            assert_actor_can_manage_organization(actor, organization, permission_key="user:create")
        return value

    def create(self, validated_data: Dict[str, Any]) -> User:
        memberships = validated_data.pop("memberships", [])
        password = validated_data.pop("password")
        request = self.context.get("request")
        actor = getattr(request, "user", None)
        with transaction.atomic():
            try:
                user = User.objects.create_user(**validated_data)
            except IntegrityError as exc:
                if "email" in str(exc).lower():
                    raise EmailAlreadyExists()
                raise InvalidUserData(detail="Unable to create user.") from exc
            user.created_by = actor
            user.updated_by = actor
            user.set_password(password)
            user.save(update_fields=["password", "created_by", "updated_by", "updated_at"])

            for membership in memberships:
                organization = membership["organization"]
                permissions = membership.get("permissions", [])
                membership_instance = UserOrganization(
                    user=user,
                    organization=organization,
                    assigned_by=actor,
                    permission_keys=permissions,
                )
                try:
                    membership_instance.full_clean()
                except ValidationError as exc:
                    raise InvalidUserData(detail=str(exc)) from exc
                membership_instance.save()
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            "full_name",
            "profile_image",
            "user_preferences",
        )

    def update(self, instance: User, validated_data: Dict[str, Any]) -> User:
        request = self.context.get("request")
        actor = getattr(request, "user", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.updated_by = actor
        try:
            instance.full_clean()
        except ValidationError as exc:  # type: ignore[name-defined]
            raise InvalidUserData(detail=str(exc)) from exc
        instance.save(update_fields=list(validated_data.keys()) + ["updated_by", "updated_at"])
        return instance


class UserStatusUpdateSerializer(serializers.Serializer):
    is_active = serializers.BooleanField()


class MembershipMutationSerializer(serializers.Serializer):
    organization = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all())
    permissions = serializers.ListField(child=serializers.CharField(), allow_empty=True, required=False)

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        request = self.context.get("request")
        actor = getattr(request, "user", None)
        organization = attrs["organization"]
        assert_actor_can_manage_organization(actor, organization, permission_key="user:manage_membership")
        return attrs

    def create(self, validated_data: Dict[str, Any]) -> UserOrganization:
        request = self.context.get("request")
        actor = getattr(request, "user", None)
        user: User = self.context["user"]
        organization = validated_data["organization"]
        permissions = list({perm.strip() for perm in validated_data.get("permissions", []) if perm.strip()})
        if UserOrganization.objects.filter(user=user, organization=organization).exists():
            raise UserAlreadyMember()
        membership = UserOrganization(
            user=user,
            organization=organization,
            assigned_by=actor,
            permission_keys=permissions,
        )
        try:
            membership.full_clean()
        except ValidationError as exc:
            raise InvalidUserData(detail=str(exc)) from exc
        membership.save()
        return membership


class MembershipRemovalSerializer(serializers.Serializer):
    organization = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all())

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        request = self.context.get("request")
        actor = getattr(request, "user", None)
        organization = attrs["organization"]
        assert_actor_can_manage_organization(actor, organization, permission_key="user:manage_membership")
        return attrs

    def remove(self) -> None:
        user: User = self.context["user"]
        organization: Organization = self.validated_data["organization"]
        try:
            membership = UserOrganization.objects.get(user=user, organization=organization)
        except UserOrganization.DoesNotExist as exc:
            raise UserNotMember() from exc
        membership.delete()
