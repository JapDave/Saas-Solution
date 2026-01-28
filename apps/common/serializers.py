from rest_framework import serializers

from apps.common.models import AuditLog


class CharFieldStrict(serializers.CharField):
    """Reject non-strings before DRF coerces them."""

    def to_internal_value(self, data):
        if not isinstance(data, str):
            raise serializers.ValidationError("Must be a string.")
        return super().to_internal_value(data)


class ErrorDetailsSerializer(serializers.Serializer):
    """Shape for the 'details' section of standardized errors."""

    user_message = serializers.CharField(required=False, allow_null=True)
    developer_message = serializers.CharField(required=False, allow_null=True)
    more_info = serializers.ListField(required=False, allow_null=True)


class ErrorSerializer(serializers.Serializer):
    """
    Standard error envelope as produced by CustomExceptionFormatter.

    This is referenced from OpenAPI for typical 4xx/5xx responses.
    """

    status = serializers.CharField()
    status_code = serializers.IntegerField()
    message = serializers.CharField()
    details = ErrorDetailsSerializer()
    timestamp = serializers.CharField()


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = [
            "id",
            "uuid",
            "created_at",
            "user",
            "method",
            "path",
            "view",
            "app_label",
            "model",
            "action",
            "object_id",
            "status_code",
            "success",
            "ip_addr",
            "user_agent",
            "trace_id",
            "span_id",
            "extra",
        ]
        read_only_fields = fields
