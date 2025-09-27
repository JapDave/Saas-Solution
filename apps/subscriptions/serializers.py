from rest_framework import serializers
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.subscriptions.models import Subscription


class SubscriptionSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "id",
            "uuid",
            "module",
            "status",
            "status_display",
            "configuration",
            "start_date",
            "end_date",
            "trial_end_date",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["uuid", "created_at", "updated_at"]

    def validate_start_date(self, value):
        """
        Validate that the start date is not in the past.
        """
        if value < timezone.now():
            err_msg = _("Start date cannot be in the past")
            raise serializers.ValidationError(err_msg)
        return value

    def validate_end_date(self, value):
        """
        Validate that the end date is not in the past.
        """
        if value < timezone.now():
            err_msg = _("End date cannot be in the past")
            raise serializers.ValidationError(err_msg)
        return value
    
    def validate(self, attrs):
        """
        Validate that the start date is before the end date.
        """
        start_date = attrs.get("start_date")
        end_date = attrs.get("end_date")

        if start_date and end_date and end_date < start_date:
            err_msg = _("End date cannot be before start date")
            raise serializers.ValidationError({"end_date": err_msg})

        return attrs
