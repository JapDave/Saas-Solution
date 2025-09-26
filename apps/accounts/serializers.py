from __future__ import annotations
from rest_framework import serializers
from .models import Account

class CharFieldStrict(serializers.CharField):
    """Reject non-strings before DRF coerces them."""
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

class AccountUpdateSerializer(serializers.ModelSerializer):
    # Optional for PATCH; include is_active toggle
    name = CharFieldStrict(required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    contact_email = serializers.EmailField(required=False)
    is_active = serializers.BooleanField(required=False)

    class Meta:
        model = Account
        fields = ("name", "description", "contact_email", "is_active")

class AccountReadSerializer(serializers.ModelSerializer):
    # expose audit fields as strings (tests expect strings)
    created_by = serializers.SerializerMethodField()
    updated_by = serializers.SerializerMethodField()

    def get_created_by(self, obj):
        return str(obj.created_by_id) if obj.created_by_id is not None else None

    def get_updated_by(self, obj):
        return str(obj.updated_by_id) if obj.updated_by_id is not None else None

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
