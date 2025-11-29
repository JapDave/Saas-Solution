from rest_framework import serializers


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
