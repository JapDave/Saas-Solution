from __future__ import annotations


from rest_framework import serializers

from apps.common.serializers import CharFieldStrict
from apps.common.exceptions import (
    CustomError,
    CustomValidationError,
    ACCOUNT_NAME_EXISTS,
    CONTACT_EMAIL_EXISTS,
    INVALID_ACCOUNT_DATA,
)
from apps.subscriptions.services import ensure_account_has_no_active_subscriptions

from .models import Account


class AccountCreateSerializer(serializers.ModelSerializer):
    """Serializer used for account creation requests."""

    """Serializer used for account creation requests."""

    name = CharFieldStrict()
    description = serializers.CharField(required=False, allow_blank=True)
    contact_email = serializers.EmailField()

    class Meta:
        model = Account
        fields = ("name", "description", "contact_email")

    def validate(self, attrs):
        name = attrs.get("name", "").strip()
        email = attrs.get("contact_email", "").strip()
        if Account.objects.filter(name__iexact=name).exists():
            raise CustomError(
                code=ACCOUNT_NAME_EXISTS,
                status_code=400,
                detail="Account name already exists in the platform",
            )
        if Account.objects.filter(contact_email__iexact=email).exists():
            raise CustomError(
                code=CONTACT_EMAIL_EXISTS,
                status_code=400,
                detail="Contact email already exists in the platform",
            )
        return attrs

    def create(self, validated_data):
        try:
            instance = Account(**validated_data)
            instance.full_clean()
            instance.save()
            return instance
        except serializers.ValidationError as exc:
            # Shape as INVALID_ACCOUNT_DATA for the handler or direct use
            raise CustomValidationError(
                detail=exc.detail,
                code=INVALID_ACCOUNT_DATA,
                status_code=400,
            )


class AccountUpdateSerializer(serializers.ModelSerializer):
    """Serializer handling full or partial account updates."""

    """Serializer handling full or partial account updates."""

    name = CharFieldStrict(required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    contact_email = serializers.EmailField(required=False)
    is_active = serializers.BooleanField(required=False)

    class Meta:
        model = Account
        fields = ("name", "description", "contact_email", "is_active")

    def validate(self, attrs):
        instance: Account = self.instance
        name = attrs.get("name")
        email = attrs.get("contact_email")
        if (
            name is not None
            and Account.objects.filter(name__iexact=name)
            .exclude(pk=instance.pk)
            .exists()
        ):
            raise CustomError(
                code=ACCOUNT_NAME_EXISTS,
                status_code=400,
                detail="Account name already exists in the platform",
            )
        if (
            email is not None
            and Account.objects.filter(contact_email__iexact=email)
            .exclude(pk=instance.pk)
            .exists()
        ):
            raise CustomError(
                code=CONTACT_EMAIL_EXISTS,
                status_code=400,
                detail="Contact email already exists in the platform",
            )
        if attrs.get("is_active") is False and instance and instance.is_active:
            ensure_account_has_no_active_subscriptions(instance)
        return attrs

    def update(self, instance, validated_data):
        for key, value in validated_data.items():
            setattr(instance, key, value)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.full_clean()
        instance.save()
        return instance


class AccountReadSerializer(serializers.ModelSerializer):
    """Read-only representation of an account instance."""

    """Read-only representation of an account instance."""

    class Meta:
        model = Account
        fields = (
            "uuid",
            "name",
            "description",
            "contact_email",
            "is_active",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
            "deleted_at",
        )
        read_only_fields = fields
