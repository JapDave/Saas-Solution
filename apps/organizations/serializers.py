from __future__ import annotations

from urllib.parse import urlparse

from django.db import IntegrityError
from django.db.models.functions import Lower
from rest_framework import serializers

from apps.accounts.models import Account
from apps.common.exceptions import (
    OrganizationNameExists,
    InvalidOrganizationData,
    InvalidLogoUrl,
)
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
    account = serializers.PrimaryKeyRelatedField(queryset=Account.objects.all(), required=False)
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
            raise InvalidLogoUrl()

    # ---- cross-field validation ---------------------------------------------

    def validate(self, attrs):
        # logo_url check first
        self._validate_logo_url(attrs.get("logo_url"))

        # Account: from payload or instance on update
        account = attrs.get("account") or (self.instance.account if self.instance else None)
        name = attrs.get("name")

        if name is not None and account is not None:
            qs = (
                Organization.objects
                .filter(account=account)
                .annotate(_lname=Lower("name"))
                .filter(_lname=name.lower())
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                # Emit coded uniqueness error
                raise OrganizationNameExists()

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
            raise OrganizationNameExists()
        except Exception:
            # Any other model validation failure -> coded invalid data
            raise InvalidOrganizationData(detail="Organization model validation failed")
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
