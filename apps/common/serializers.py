from rest_framework import serializers

class CharFieldStrict(serializers.CharField):
    """Reject non-strings before DRF coerces them."""
    def to_internal_value(self, data):
        if not isinstance(data, str):
            raise serializers.ValidationError("Must be a string.")
        return super().to_internal_value(data)