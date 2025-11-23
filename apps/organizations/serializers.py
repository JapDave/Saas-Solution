from __future__ import annotations

from urllib.parse import urlparse

from django.db import IntegrityError
from django.db.models.functions import Lower
from rest_framework import serializers
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.accounts.models import Account
from apps.common.exceptions import (
    CustomError,
    CustomValidationError,
    ORGANIZATION_NAME_EXISTS,
    INVALID_ORGANIZATION_DATA,
    INVALID_LOGO_URL,
)
from apps.subscriptions.services import ensure_organization_has_no_active_subscriptions
from apps.subscriptions.services import ensure_organization_has_no_active_subscriptions
from .models import Organization


class CharFieldStrict(serializers.CharField):
    """Reject non-strings before DRF coerces them."""

    def to_internal_value(self, data):
        if not isinstance(data, str):
            raise serializers.ValidationError("Must be a string.")
        return super().to_internal_value(data)


class _BaseOrgSerializer(serializers.ModelSerializer):
    """
    Shared validation + create/update that enforce:
      - (account, name) case-insensitive uniqueness (excluding self on update)
      - basic logo_url sanity
      - model.full_clean() before save
      - DB IntegrityError mapped to ORGANIZATION_NAME_EXISTS
    """

    account = serializers.PrimaryKeyRelatedField(
        queryset=Account.objects.all(), required=False
    )
    name = CharFieldStrict(required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    logo_url = serializers.URLField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)

    class Meta:
        model = Organization
        fields = ("account", "name", "description", "logo_url", "is_active")

    # ---- helpers -------------------------------------------------------------

    def _validate_logo_url(self, value: str | None) -> None:
        """
        We keep it lightweight: enforce http/https scheme if provided.
        (We do not make network calls in serializers.)
        """
        if not value:
            return
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            # Emit coded error
            raise CustomError(
                code=INVALID_LOGO_URL,
                status_code=400,
                detail="Logo URL is invalid or inaccessible",
            )

    # ---- cross-field validation ---------------------------------------------

    def validate(self, attrs):
        # logo_url check first
        self._validate_logo_url(attrs.get("logo_url"))

        # Account: from payload or instance on update
        account = attrs.get("account") or (
            self.instance.account if self.instance else None
        )
        name = attrs.get("name")

        if name is not None and account is not None:
            qs = (
                Organization.objects.filter(account=account)
                .annotate(_lname=Lower("name"))
                .filter(_lname=name.lower())
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                # Duplicate within same account
                # Raise domain-specific code for serializer tests
                status = 409 if not self.instance else 400
                raise CustomError(
                    code=ORGANIZATION_NAME_EXISTS,
                    status_code=status,
                    detail="Organization name already exists in the account",
                )

        if (
            attrs.get("is_active") is False
            and self.instance
            and self.instance.is_active
        ):
            ensure_organization_has_no_active_subscriptions(self.instance)

        if (
            attrs.get("is_active") is False
            and self.instance
            and self.instance.is_active
        ):
            ensure_organization_has_no_active_subscriptions(self.instance)

        return attrs

    # ---- persistence with model.full_clean() --------------------------------

    def _apply(self, instance: Organization, attrs: dict) -> Organization:
        for k, v in attrs.items():
            setattr(instance, k, v)
        try:
            instance.full_clean()
            instance.save()
        except IntegrityError:
            # Safety net if DB unique catches something our check missed
            status = 409 if not self.instance else 400
            raise CustomError(
                code=ORGANIZATION_NAME_EXISTS,
                status_code=status,
                detail="Organization name already exists in the account",
            )
        except Exception as exc:
            # Any other model validation failure -> coded invalid data
            raise CustomValidationError(
                detail={"detail": "Organization model validation failed"},
                code=INVALID_ORGANIZATION_DATA,
                status_code=400,
            ) from exc
        return instance

    def create(self, validated_data):
        instance = Organization(**validated_data)
        return self._apply(instance, validated_data)

    def update(self, instance, validated_data):
        return self._apply(instance, validated_data)


class OrganizationCreateSerializer(_BaseOrgSerializer):
    # Required on create
    account = serializers.PrimaryKeyRelatedField(queryset=Account.objects.all())
    name = CharFieldStrict()


class OrganizationUpdateSerializer(_BaseOrgSerializer):
    # Optional on PATCH; required fields enforced only if provided
    pass


class OrganizationReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = (
            "id",
            "account",
            "name",
            "description",
            "logo_url",
            "is_active",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
            "deleted_at",
        )
        read_only_fields = fields


from django.contrib.auth import get_user_model

from apps.roles.constants import ROLE_ORGANIZATION_OWNER
from apps.roles.models import RoleAssignment
from apps.users.models import UserOrganization

User = get_user_model()


class OrganizationOwnerAssignSerializer(serializers.Serializer):
    user = serializers.UUIDField()

    def validate_user(self, value):
        try:
            user = User.objects.get(uuid=value)
        except User.DoesNotExist as exc:
            raise serializers.ValidationError("User does not exist.") from exc
        if not user.is_active:
            raise serializers.ValidationError("User must be active.")
        return user

    def validate(self, attrs):
        organization = self.context["organization"]
        user = attrs["user"]
        membership_exists = UserOrganization.objects.filter(
            user=user,
            organization=organization,
            is_active=True,
            deleted_at__isnull=True,
        ).exists()
        if not membership_exists:
            raise serializers.ValidationError(
                {"user": "User must be an active member of the organization."}
            )
        return attrs


class OrganizationOwnerTransferSerializer(serializers.Serializer):
    new_owner = serializers.UUIDField()
    current_owner = serializers.UUIDField(required=False)

    def _resolve_user(self, value, field_name):
        try:
            user = User.objects.get(uuid=value)
        except User.DoesNotExist as exc:
            raise serializers.ValidationError(
                {field_name: "User does not exist."}
            ) from exc
        if not user.is_active:
            raise serializers.ValidationError({field_name: "User must be active."})
        return user

    def validate(self, attrs):
        organization = self.context["organization"]
        attrs["new_owner"] = self._resolve_user(attrs["new_owner"], "new_owner")
        current_value = attrs.get("current_owner")
        if current_value is not None:
            attrs["current_owner"] = self._resolve_user(current_value, "current_owner")
            is_owner = RoleAssignment.objects.filter(
                organization=organization,
                user=attrs["current_owner"],
                role__name=ROLE_ORGANIZATION_OWNER,
                is_active=True,
                deleted_at__isnull=True,
            ).exists()
            if not is_owner:
                raise serializers.ValidationError(
                    {
                        "current_owner": "Current owner must hold the Organization Owner role."
                    }
                )
        membership_exists = UserOrganization.objects.filter(
            user=attrs["new_owner"],
            organization=organization,
            is_active=True,
            deleted_at__isnull=True,
        ).exists()
        if not membership_exists:
            raise serializers.ValidationError(
                {"new_owner": "User must be an active member of the organization."}
            )
        return attrs
