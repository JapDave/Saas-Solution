from __future__ import annotations
from rest_framework import serializers
from .models import Account


class AccountCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = ("name", "description", "contact_email")


class AccountUpdateSerializer(serializers.ModelSerializer):
    # all optional for partial updates; include is_active so activate/deactivate is handled via CRUD
    name = serializers.CharField(required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    contact_email = serializers.EmailField(required=False)
    is_active = serializers.BooleanField(required=False)

    class Meta:
        model = Account
        fields = ("name", "description", "contact_email", "is_active")


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
