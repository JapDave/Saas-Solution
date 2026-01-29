from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone

from django.utils import timezone
from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.authentication.serializers import (
    ContextSwitchSerializer,
    LogoutSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    SessionTokenObtainPairSerializer,
    SessionTokenRefreshSerializer,
)
from apps.authentication.throttles import (
    ContextSwitchRateThrottle,
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


@extend_schema(tags=["Auth"])
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


@extend_schema(tags=["Auth"])
class SessionTokenRefreshView(TokenRefreshView):
    permission_classes = [AllowAny]
    serializer_class = SessionTokenRefreshSerializer
    throttle_classes = [RefreshRateThrottle]


@extend_schema(tags=["Auth"])
class SessionLogoutView(APIView):
    throttle_classes = [LogoutRateThrottle]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"status": "ok"}, status=status.HTTP_205_RESET_CONTENT)


@extend_schema(tags=["Auth"])
class ContextSwitchView(APIView):
    throttle_classes = [ContextSwitchRateThrottle]

    def post(self, request):
        serializer = ContextSwitchSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        membership = serializer.validated_data["membership"]

        # Deactivate current session (best-effort)
        current_session = getattr(request, "auth_session", None)
        if current_session:
            try:
                current_session.deactivate(reason="context_switch")
            except Exception:
                pass

        # Issue fresh token pair scoped to new org context
        refresh = RefreshToken.for_user(request.user)
        access = refresh.access_token
        access["active_organization_id"] = membership.organization_id
        refresh["active_organization_id"] = membership.organization_id

        # Adjust refresh lifetime based on org subscription config
        hours = session_duration_hours(membership.organization_id)
        refresh.set_exp(lifetime=timedelta(hours=hours))

        # Persist a new session row
        session = AuthSession.objects.create(
            user=request.user,
            access_jti=access["jti"],
            refresh_jti=refresh["jti"],
            access_expires_at=datetime.fromtimestamp(access["exp"], tz=dt_timezone.utc),
            refresh_expires_at=datetime.fromtimestamp(refresh["exp"], tz=dt_timezone.utc),
            ip_address=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
        )

        return Response(
            {
                "access": str(access),
                "refresh": str(refresh),
                "session_id": str(session.id),
                "active_organization_id": membership.organization_id,
            },
            status=status.HTTP_200_OK,
        )


@extend_schema(tags=["Auth"])
class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        # In production we would send an email; return token/uid for testing only.
        return Response({"sent": True, **{k: v for k, v in result.items() if k in {"uid", "token"}}})


@extend_schema(tags=["Auth"])
class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"status": "password_reset_success"})
