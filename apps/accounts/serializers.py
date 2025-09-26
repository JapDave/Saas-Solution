from __future__ import annotations
from rest_framework import serializers
from .models import Account
from apps.common.exceptions import AccountNameExists, ContactEmailExists, InvalidAccountData

class CharFieldStrict(serializers.CharField):
    def to_internal_value(self, data):
        if not isinstance(data, str):
            raise serializers.ValidationError("Must be a string.")
        return super().to_internal_value(data)

class AccountCreateSerializer(serializers.ModelSerializer):
    name = CharFieldStrict()
    description = serializers.CharField(required=False, allow_blank=True)
    contact_email = serializers.EmailField()

    class Meta:
        model = Account
        fields = ("name", "description", "contact_email")

    def validate(self, attrs):
        name = attrs.get("name", "").strip()
        email = attrs.get("contact_email", "").strip()
        # Case-insensitive unique checks (exclude soft-deleted if your model supports it)
        if Account.objects.filter(name__iexact=name).exists():
            raise AccountNameExists()
        if Account.objects.filter(contact_email__iexact=email).exists():
            raise ContactEmailExists()
        return attrs

    def create(self, validated_data):
        try:
            obj = Account(**validated_data)
            obj.full_clean()
            obj.save()
            return obj
        except serializers.ValidationError as e:
            # Wrap unlikely model validation into a coded error
            raise InvalidAccountData(detail="Account model validation failed", code=None)


class AccountUpdateSerializer(serializers.ModelSerializer):
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
        if name is not None:
            if Account.objects.filter(name__iexact=name).exclude(pk=instance.pk).exists():
                raise AccountNameExists()
        if email is not None:
            if Account.objects.filter(contact_email__iexact=email).exclude(pk=instance.pk).exists():
                raise ContactEmailExists()
        return attrs

    def update(self, instance, validated_data):
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.full_clean()
        instance.save()
        return instance


class AccountReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = (
            "id",
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
