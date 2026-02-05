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
from apps.common.exceptions import CustomError, CONTEXT_SWITCH_FORBIDDEN, SESSION_REVOKED, RATE_LIMIT_EXCEEDED, INVALID_CREDENTIALS
from apps.authentication.models import AuthSession
from apps.users.models import UserOrganization
from rest_framework_simplejwt.tokens import RefreshToken
from apps.authentication.rate_limit import (
    check_login_rate_limit,
    record_login_failure,
    clear_login_failures,
    check_refresh_rate_limit,
    record_refresh_attempt,
    check_password_reset_rate_limit,
    record_password_reset_attempt,
)
from apps.authentication.serializers import _session_duration_hours as session_duration_hours  # type: ignore


def _apply_delay(kind: str = "REQUEST"):
    import random
    import time

    delay = random.uniform(0, 1)
    if delay > 0:
        time.sleep(delay)


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
        password = request.data.get("password") or ""
        if not email or not password or len(password) < 6 or len(password) > 128:
            _apply_delay("LOGIN")
            return Response(
                {"code": INVALID_CREDENTIALS, "message": "Invalid email or password."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ip = request.META.get("REMOTE_ADDR")
        limit = getattr(settings, "AUTH_LOGIN_RATE_LIMIT_ATTEMPTS", 3) or 3
        window = getattr(settings, "AUTH_LOGIN_RATE_LIMIT_WINDOW_MINUTES", 10) or 10

        blocked, retry_after = check_login_rate_limit(email=email, ip=ip, limit=limit, window_minutes=window)
        if blocked:
            return Response(
                {"code": RATE_LIMIT_EXCEEDED, "message": "Too many failed login attempts. Try later."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
                headers={"Retry-After": str(retry_after)},
            )
        try:
            serializer = self.get_serializer(data=request.data, context=self.get_serializer_context())
            serializer.is_valid(raise_exception=True)
            response = Response(serializer.validated_data, status=status.HTTP_200_OK)
            clear_login_failures(email=email, ip=ip)
            # back-fill audit log user
            from apps.common.audit import get_audit_context

            ctx = get_audit_context()
            if ctx.audit_log and not ctx.audit_log.user_id:
                ctx.audit_log.user = serializer.user
                ctx.audit_log._allow_update = True
                ctx.audit_log.save(update_fields=["user"])
            return response
        except Exception as exc:
            # On any auth failure, record it; re-raise.
            _apply_delay("LOGIN")
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

    def post(self, request, *args, **kwargs):
        ip = request.META.get("REMOTE_ADDR")
        # pre-parse refresh to get user_id for rate limit; failures will be handled by serializer
        user_id = None
        raw_refresh = request.data.get("refresh")
        from rest_framework_simplejwt.tokens import RefreshToken

        try:
            rt = RefreshToken(raw_refresh)
            user_id = rt.get("user_id")
        except Exception:
            user_id = None
        blocked, retry_after = check_refresh_rate_limit(ip=ip, user_id=user_id, limit=None, window_minutes=None)
        if blocked:
            return Response(
                {"code": RATE_LIMIT_EXCEEDED, "message": "Too many refresh attempts. Try later."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
                headers={"Retry-After": str(retry_after)},
            )
        record_refresh_attempt(ip=ip, user_id=user_id, limit=None, window_minutes=None)
        try:
            return super().post(request, *args, **kwargs)
        except Exception:
            _apply_delay("REFRESH")
            raise


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
    permission_classes = [AllowAny]

    def post(self, request):
        # Spec: logout by access token if present, otherwise accept refresh token fallback
        session = getattr(request, "auth_session", None)
        if session:
            session.deactivate(reason="logout")
            return Response(status=status.HTTP_204_NO_CONTENT, headers={"X-Access-JTI": session.token_jti})
        if request.data.get("refresh"):
            serializer = LogoutSerializer(data=request.data)
            try:
                serializer.is_valid(raise_exception=True)
                result = serializer.save()
            except Exception:
                _apply_delay("LOGOUT")
                raise
            headers = {}
            if result and isinstance(result, dict):
                headers["X-Access-JTI"] = result.get("access_jti", "")
            return Response(status=status.HTTP_204_NO_CONTENT, headers=headers)
        raise CustomError(code=SESSION_REVOKED, detail="No active session to logout.", status_code=400)




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
        email = (request.data.get("email") or "").lower()
        ip = request.META.get("REMOTE_ADDR")
        blocked, retry_after = check_password_reset_rate_limit(email=email, ip=ip, limit=3, window_minutes=60)
        if blocked:
            return Response(
                {"code": RATE_LIMIT_EXCEEDED, "message": "Too many reset requests. Try later."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
                headers={"Retry-After": str(retry_after)},
            )
        record_password_reset_attempt(email=email, ip=ip, limit=3, window_minutes=60)
        serializer = PasswordResetRequestSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            serializer.save()
        except Exception:
            _apply_delay("PASSWORD_RESET")
            raise
        return Response(
            {"message": "If an account exists for this email address, you will receive a password reset email shortly."},
            status=status.HTTP_200_OK,
        )


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
        try:
            serializer.is_valid(raise_exception=True)
            serializer.save()
        except Exception:
            _apply_delay("PASSWORD_RESET")
            raise
        return Response({"status": "password_reset_success"})


