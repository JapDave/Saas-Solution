from rest_framework import serializers
from .models.account import Account

class AccountReadSerializer(serializers.ModelSerializer):
    accountId = serializers.UUIDField(source="account_id", read_only=True)
    contactEmail = serializers.EmailField(source="contact_email")
    isActive = serializers.SerializerMethodField()

    class Meta:
        model = Account
        fields = (
            "accountId",
            "name",
            "description",
            "contactEmail",
            "state",
            "isActive",
            "created_by",
            "created_at",
            "updated_at",
            "deleted_at",
        )
        read_only_fields = ("created_by", "created_at", "updated_at", "deleted_at")

    def get_isActive(self, obj):
        return obj.is_active

class AccountWriteSerializer(serializers.ModelSerializer):
    contactEmail = serializers.EmailField(source="contact_email")

    class Meta:
        model = Account
        fields = ("name", "description", "contactEmail")

class AccountUpdateSerializer(serializers.ModelSerializer):
    contactEmail = serializers.EmailField(source="contact_email", required=False)
    name = serializers.CharField(required=False)
    description = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Account
        fields = ("name", "description", "contactEmail")
