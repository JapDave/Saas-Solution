from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone

from django.utils import timezone
from django.conf import settings
from drf_spectacular.utils import (
    extend_schema,
    inline_serializer,
    OpenApiResponse,
)
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework import serializers

from apps.authentication.serializers import (
    LogoutSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    SessionTokenObtainPairSerializer,
    SessionTokenRefreshSerializer,
)
from apps.authentication.throttles import (
    LoginRateThrottle,
    LogoutRateThrottle,
    PasswordResetRateThrottle,
    RefreshRateThrottle,
)
from apps.common.exceptions import CustomError, CONTEXT_SWITCH_FORBIDDEN, SESSION_REVOKED, LOGIN_RATE_LIMIT
from apps.authentication.models import AuthSession
from apps.users.models import UserOrganization
from rest_framework_simplejwt.tokens import RefreshToken
from apps.authentication.rate_limit import (
    check_login_rate_limit,
    record_login_failure,
    clear_login_failures,
)
from apps.subscriptions.models import Subscription
from django.db.models import Q
from apps.authentication.serializers import _session_duration_hours as session_duration_hours  # type: ignore


@extend_schema(
    tags=["Auth"],
    request=SessionTokenObtainPairSerializer,
    responses=OpenApiResponse(
        response=inline_serializer(
            name="SessionTokenObtainPairResponse",
            fields={
                "access": serializers.CharField(),
                "refresh": serializers.CharField(),
                "session_id": serializers.UUIDField(),
            },
        )
    ),
)
class SessionTokenObtainPairView(TokenObtainPairView):
    permission_classes = [AllowAny]
    serializer_class = SessionTokenObtainPairSerializer
    throttle_classes = []  # handled manually for rolling window

    def post(self, request, *args, **kwargs):
        email = (request.data.get("email") or "").strip().lower()
        ip = request.META.get("REMOTE_ADDR")
        # Resolve org-scoped limits (strictest across memberships); no env defaults if org configs exist
        limit = getattr(settings, "AUTH_LOGIN_RATE_LIMIT_ATTEMPTS", 3) or 3
        window = getattr(settings, "AUTH_LOGIN_RATE_LIMIT_WINDOW_MINUTES", 10) or 10
        try:
            if email:
                from django.contrib.auth import get_user_model

                User = get_user_model()
                user = User.objects.filter(email__iexact=email, is_active=True).first()
                if user:
                    now = timezone.now()
                    org_ids = list(
                        user.memberships.filter(is_active=True, deleted_at__isnull=True).values_list(
                            "organization_id", flat=True
                        )
                    )
                    subs = (
                        Subscription.objects.filter(
                            organization_id__in=org_ids,
                            status__in=[Subscription.Status.ACTIVE, Subscription.Status.TRIAL],
                            start_date__lte=now,
                        )
                        .filter(Q(end_date__isnull=True) | Q(end_date__gt=now))
                        .values_list("configuration", flat=True)
                    )
                    limits = []
                    windows = []
                    for cfg in subs:
                        if isinstance(cfg, dict):
                            if cfg.get("rate_limit_login_attempts") is not None:
                                limits.append(int(cfg.get("rate_limit_login_attempts")))
                            if cfg.get("rate_limit_window_minutes") is not None:
                                windows.append(int(cfg.get("rate_limit_window_minutes")))
                    if limits:
                        limit = min([l for l in limits if l > 0])
                    if windows:
                        window = max([w for w in windows if w > 0])
        except Exception:
            pass

        blocked, retry_after = check_login_rate_limit(email=email, ip=ip, limit=limit, window_minutes=window)
        if blocked:
            return Response(
                {"code": LOGIN_RATE_LIMIT, "message": "Too many failed login attempts. Try later."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
                headers={"Retry-After": str(retry_after)},
            )
        try:
            response = super().post(request, *args, **kwargs)
            clear_login_failures(email=email, ip=ip)
            return response
        except Exception as exc:
            # On any auth failure, record it; re-raise.
            record_login_failure(email=email, ip=ip, limit=limit, window_minutes=window)
            raise


@extend_schema(
    tags=["Auth"],
    request=SessionTokenRefreshSerializer,
    responses=OpenApiResponse(
        response=inline_serializer(
            name="SessionTokenRefreshResponse",
            fields={
                "access": serializers.CharField(),
                "session_id": serializers.UUIDField(),
            },
        )
    ),
)
class SessionTokenRefreshView(TokenRefreshView):
    permission_classes = [AllowAny]
    serializer_class = SessionTokenRefreshSerializer
    throttle_classes = [RefreshRateThrottle]


@extend_schema(
    tags=["Auth"],
    request=LogoutSerializer,
    responses=OpenApiResponse(
        response=inline_serializer(
            name="SessionLogoutResponse",
            fields={"status": serializers.CharField()},
        )
    ),
)
class SessionLogoutView(APIView):
    throttle_classes = [LogoutRateThrottle]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"status": "ok"}, status=status.HTTP_205_RESET_CONTENT)




@extend_schema(
    tags=["Auth"],
    request=PasswordResetRequestSerializer,
    responses=OpenApiResponse(
        response=inline_serializer(
            name="PasswordResetRequestResponse",
            fields={
                "sent": serializers.BooleanField(),
                # uid/token are only returned in non-prod/testing contexts
                "uid": serializers.CharField(required=False),
                "token": serializers.CharField(required=False),
            },
        )
    ),
)
class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        # In production we would send an email; return token/uid for testing only.
        return Response({"sent": True, **{k: v for k, v in result.items() if k in {"uid", "token"}}})


@extend_schema(
    tags=["Auth"],
    request=PasswordResetConfirmSerializer,
    responses=OpenApiResponse(
        response=inline_serializer(
            name="PasswordResetConfirmResponse",
            fields={"status": serializers.CharField()},
        )
    ),
)
class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"status": "password_reset_success"})
