from __future__ import annotations

from typing import Any, Dict, Iterable, List

from uuid import UUID

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.common.exceptions import (
    CustomError,
    CustomValidationError,
    EMAIL_ALREADY_EXISTS,
    INVALID_USER_DATA,
    USER_ALREADY_MEMBER,
    USER_NOT_MEMBER,
)
from apps.organizations.models import Organization
from apps.roles.constants import ROLE_ORGANIZATION_OWNER
from apps.roles.services import sync_user_role_assignments
from apps.roles.utils import has_role
from apps.roles.models import Role, RoleAssignment

from .models import UserOrganization
from .services import ensure_user_can_manage_organization

User = get_user_model()



def _normalize_permission_keys(values: Iterable[str]) -> List[str]:
    normalized: List[str] = []
    seen: set[str] = set()
    for value in values or []:
        if not isinstance(value, str):
            continue
        token = value.strip().lower()
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    normalized.sort()
    return normalized


def _collect_permissions_from_roles(roles: Iterable[Role]) -> List[str]:
    collected: List[str] = []
    for role in roles or []:
        collected.extend(role.permissions or [])
    return _normalize_permission_keys(collected)


def _merge_permission_keys(*groups: Iterable[str]) -> List[str]:
    combined: List[str] = []
    for group in groups:
        combined.extend(group or [])
    return _normalize_permission_keys(combined)


def _resolve_roles_for_membership(*, organization: Organization, role_ids: Iterable[Any]) -> List[Role]:
    if not role_ids:
        raise CustomValidationError(detail='At least one role must be assigned to the organization membership.', code=INVALID_USER_DATA)

    try:
        uuids = [UUID(str(value)) for value in role_ids]
    except (TypeError, ValueError) as exc:
        raise CustomValidationError(detail='Role identifiers must be valid UUID strings.', code=INVALID_USER_DATA) from exc

    roles = list(Role.objects.filter(uuid__in=uuids))
    if len({role.uuid for role in roles}) != len({UUID(str(value)) for value in role_ids}):
        existing = {role.uuid for role in roles}
        missing = [str(uuid) for uuid in uuids if uuid not in existing]
        raise CustomValidationError(detail=f"Roles not found: {', '.join(missing)}", code=INVALID_USER_DATA)

    invalid = [role for role in roles if role.organization_id != organization.id]
    if invalid:
        raise CustomValidationError(detail='All roles must belong to the target organization.', code=INVALID_USER_DATA)

    inactive = [role for role in roles if not role.is_active]
    if inactive:
        raise CustomValidationError(detail='Inactive roles cannot be assigned.', code=INVALID_USER_DATA)

    ordered: List[Role] = []
    seen_ids: set[int] = set()
    role_map = {role.uuid: role for role in roles}
    for uuid_key in uuids:
        role = role_map.get(uuid_key)
        if role and role.id not in seen_ids:
            ordered.append(role)
            seen_ids.add(role.id)
    return ordered


class MembershipSerializer(serializers.ModelSerializer):
    organization_uuid = serializers.UUIDField(source="organization.uuid", read_only=True)
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    account_uuid = serializers.UUIDField(source="organization.account.uuid", read_only=True)
    permissions = serializers.ListField(child=serializers.CharField(), source="permission_keys", read_only=True)
    roles = serializers.SerializerMethodField()

    def get_roles(self, obj):
        assignments = RoleAssignment.objects.filter(
            user=obj.user,
            organization=obj.organization,
            deleted_at__isnull=True,
            is_active=True,
        ).select_related("role").order_by("role__name")
        return [
            {"uuid": str(assignment.role.uuid), "name": assignment.role.name}
            for assignment in assignments
        ]

    class Meta:
        model = UserOrganization
        fields = (
            "uuid",
            "organization_uuid",
            "organization_name",
            "account_uuid",
            "permissions",
            "roles",
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
    roles = serializers.ListField(child=serializers.UUIDField(), allow_empty=False, required=False)

    def validate_permissions(self, permissions: Iterable[str]):
        return _normalize_permission_keys(permissions)

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        organization = attrs["organization"]
        raw_role_values = attrs.get("roles")
        if raw_role_values is None:
            raw_role_values = getattr(self, "initial_data", {}).get("roles")
        role_ids = [str(value) for value in (raw_role_values or [])]
        roles = _resolve_roles_for_membership(organization=organization, role_ids=role_ids)
        attrs["roles"] = roles
        attrs["permissions"] = _merge_permission_keys(attrs.get("permissions", []), _collect_permissions_from_roles(roles))
        return attrs


class UserReadSerializer(serializers.ModelSerializer):
    memberships = MembershipSerializer(many=True, read_only=True)

    class Meta:
        model = User
        fields = (
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

    def is_valid(self, *, raise_exception=False):
        try:
            return super().is_valid(raise_exception=raise_exception)
        except DRFValidationError as exc:
            if raise_exception:
                detail = exc.detail
                membership_error = None
                if isinstance(detail, dict):
                    membership_error = detail.get("memberships")
                if membership_error is not None:
                    message = None
                    if isinstance(membership_error, dict):
                        message = membership_error.get("message") or membership_error.get("detail")
                    elif isinstance(membership_error, list) and membership_error:
                        first = membership_error[0]
                        if isinstance(first, dict):
                            message = first.get("message") or first.get("detail")
                        else:
                            message = str(first)
                    raise CustomValidationError(
                        detail=message or "User membership data validation failed.",
                        code=INVALID_USER_DATA,
                    ) from exc
            raise

    def validate_email(self, value: str) -> str:
        if User.objects.with_deleted().filter(email__iexact=value).exists():
            raise CustomError(code=EMAIL_ALREADY_EXISTS, status_code=409, detail='Email address is already in use')
        return value

    def validate_password(self, value: str) -> str:
        if not isinstance(value, str) or not 8 <= len(value) <= 128:
            raise CustomValidationError(detail="Password must be between 8 and 128 characters.", code=INVALID_USER_DATA)
        return value

    def validate_memberships(self, value: List[Dict[str, Any]]):
        if not value:
            raise CustomValidationError(detail="User must be assigned to at least one organization.", code=INVALID_USER_DATA)
        request = self.context.get("request")
        request_user = getattr(request, "user", None)
        if request_user is None:
            raise CustomValidationError(detail="request_user context required.", code=INVALID_USER_DATA)
        seen_orgs = set()
        for item in value:
            organization = item.get("organization")
            if organization is None:
                raise CustomValidationError(detail="Organization membership entry is missing organization reference.", code=INVALID_USER_DATA)
            if organization.id in seen_orgs:
                raise CustomValidationError(detail="Duplicate organization entries are not allowed.", code=INVALID_USER_DATA)
            seen_orgs.add(organization.id)
            ensure_user_can_manage_organization(request_user, organization, permission_key="user:create")
        return value

    def create(self, validated_data: Dict[str, Any]) -> User:
        memberships = validated_data.pop("memberships", [])
        password = validated_data.pop("password")
        request = self.context.get("request")
        request_user = getattr(request, "user", None)
        with transaction.atomic():
            try:
                user = User.objects.create_user(password=password, **validated_data)
            except IntegrityError as exc:
                if "email" in str(exc).lower():
                    raise CustomError(code=EMAIL_ALREADY_EXISTS, status_code=409, detail='Email address is already in use')
                raise CustomValidationError(detail="Unable to create user.", code=INVALID_USER_DATA) from exc
            user.created_by = request_user
            user.updated_by = request_user
            user.set_password(password)
            user.save(update_fields=["password", "created_by", "updated_by", "updated_at"])

            for membership in memberships:
                organization = membership["organization"]
                roles = membership.get("roles", [])
                permissions = list(membership.get("permissions", []))
                membership_instance = UserOrganization(
                    user=user,
                    organization=organization,
                    assigned_by=request_user,
                    permission_keys=permissions,
                )
                try:
                    membership_instance.full_clean()
                except ValidationError as exc:
                    raise CustomValidationError(detail=str(exc), code=INVALID_USER_DATA) from exc
                membership_instance.save()
                sync_user_role_assignments(
                    user=user,
                    organization=organization,
                    roles=roles,
                    assigned_by=request_user,
                )
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
        request_user = getattr(request, "user", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.updated_by = request_user
        try:
            instance.full_clean()
        except ValidationError as exc:  # type: ignore[name-defined]
            from apps.common.exceptions import CustomValidationError, INVALID_USER_DATA
            raise CustomValidationError(detail=str(exc), code=INVALID_USER_DATA) from exc
        instance.save(update_fields=list(validated_data.keys()) + ["updated_by", "updated_at"])
        return instance


class UserStatusUpdateSerializer(serializers.Serializer):
    is_active = serializers.BooleanField()


class MembershipMutationSerializer(serializers.Serializer):
    organization = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all())
    permissions = serializers.ListField(child=serializers.CharField(), allow_empty=True, required=False)
    roles = serializers.ListField(child=serializers.UUIDField(), allow_empty=False, required=False)

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        request = self.context.get("request")
        request_user = getattr(request, "user", None)
        organization = attrs["organization"]
        ensure_user_can_manage_organization(request_user, organization, permission_key="user:manage_membership")
        raw_role_values = attrs.get("roles")
        if raw_role_values is None:
            raw_role_values = getattr(self, "initial_data", {}).get("roles")
        role_ids = [str(value) for value in (raw_role_values or [])]
        roles: List[Role] = []
        if role_ids:
            roles = _resolve_roles_for_membership(organization=organization, role_ids=role_ids)
        attrs["roles"] = roles
        attrs["permissions"] = _merge_permission_keys(attrs.get("permissions", []), _collect_permissions_from_roles(roles))
        user = self.context.get("user")
        if user is None:
            raise CustomValidationError(detail="user context required.", code=INVALID_USER_DATA)
        if UserOrganization.objects.filter(user=user, organization=organization).exists():
            raise CustomError(code=USER_ALREADY_MEMBER, status_code=409, detail='User is already a member of the organization')
        return attrs

    def create(self, validated_data: Dict[str, Any]) -> UserOrganization:
        request = self.context.get("request")
        request_user = getattr(request, "user", None)
        if request_user is None:
            raise CustomValidationError(detail="request_user context required.", code=INVALID_USER_DATA)
        user: User = self.context["user"]
        organization = validated_data["organization"]
        if UserOrganization.objects.filter(user=user, organization=organization).exists():
            raise CustomError(code=USER_ALREADY_MEMBER, status_code=409, detail='User is already a member of the organization')
        roles = validated_data.get("roles", [])
        permissions = list(validated_data.get("permissions", []))
        membership = UserOrganization(
            user=user,
            organization=organization,
            assigned_by=request_user,
            permission_keys=permissions,
        )
        try:
            membership.full_clean()
        except ValidationError as exc:
            raise CustomValidationError(detail=str(exc), code=INVALID_USER_DATA) from exc
        membership.save()
        sync_user_role_assignments(
            user=user,
            organization=organization,
            roles=roles,
            assigned_by=request_user,
        )
        return membership


class MembershipRemovalSerializer(serializers.Serializer):
    organization = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all())

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        request = self.context.get("request")
        request_user = getattr(request, "user", None)
        organization = attrs["organization"]
        ensure_user_can_manage_organization(request_user, organization, permission_key="user:manage_membership")
        return attrs

    def remove(self) -> None:
        user: User = self.context["user"]
        organization: Organization = self.validated_data["organization"]
        try:
            membership = UserOrganization.objects.get(user=user, organization=organization)
        except UserOrganization.DoesNotExist as exc:
            raise CustomError(code=USER_NOT_MEMBER, status_code=400, detail='User is not a member of the organization') from exc

        org_uuid = str(getattr(organization, "uuid", ""))
        try:
            is_owner = has_role(user, ROLE_ORGANIZATION_OWNER, org_uuid)
        except ValueError:
            is_owner = False

        if is_owner:
            remaining_owner_exists = RoleAssignment.objects.filter(
                organization=organization,
                role__name=ROLE_ORGANIZATION_OWNER,
                is_active=True,
                deleted_at__isnull=True,
            ).exclude(user=user).exists()
            if not remaining_owner_exists:
                raise serializers.ValidationError(
                    {"organization": _("Organization must retain at least one owner.")}
                )

        assignments = RoleAssignment.objects.filter(
            user=user,
            organization=organization,
            deleted_at__isnull=True,
        ).select_related("role")
        for assignment in assignments:
            assignment.delete()

        membership.delete()




