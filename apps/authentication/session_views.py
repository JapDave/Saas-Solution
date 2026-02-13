from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils import timezone

from apps.authentication.models import AuthSession


class SessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuthSession
        fields = [
            "id",
            "token_jti",
            "refresh_token_hash",
            "access_expires_at",
            "last_activity_at",
            "deactivated_at",
            "deactivated_reason",
            "ip_address",
            "user_agent",
            "created_at",
        ]


class SessionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        now = timezone.now()
        qs = AuthSession.objects.filter(
            user=request.user,
            access_expires_at__gt=now,
        ).order_by("-created_at")
        data = SessionSerializer(qs, many=True).data
        return Response(data)
