from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Any, Optional

from django.conf import settings
from django.utils import timezone
from django.core.mail import send_mail
from django.urls import reverse
from rest_framework import serializers
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from rest_framework_simplejwt.serializers import (
    TokenObtainPairSerializer,
    TokenRefreshSerializer,
)
from rest_framework_simplejwt.tokens import RefreshToken

from apps.authentication.models import AuthSession
from apps.common.exceptions import (
    CustomError,
    INVALID_CREDENTIALS,
    SESSION_CONCURRENCY_LIMIT,
    SESSION_EXPIRED,
    SESSION_REVOKED,
    PASSWORD_POLICY_VIOLATION,
)
from apps.users.models import UserOrganization
from apps.subscriptions.models import Subscription
from django.db.models import Q
from django.contrib.auth import get_user_model

User = get_user_model()


def _client_ip(request) -> str | None:
    if not request:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.META.get("REMOTE_ADDR")


def _user_agent(request) -> str:
    if not request:
        return ""
    ua = request.META.get("HTTP_USER_AGENT", "") or ""
    return ua[:500]


def _dt_from_timestamp(ts: Any) -> datetime:
    return datetime.fromtimestamp(int(ts), tz=dt_timezone.utc)


def _session_duration_hours(org_id: Optional[int]) -> int:
    """Resolve session duration (refresh lifetime) from active subscription config (no env fallback)."""
    if not org_id:
        raise CustomError(code=SESSION_EXPIRED, detail="Organization context required for session duration.", status_code=400)
    now = timezone.now()
    sub = (
        Subscription.objects.filter(
            organization_id=org_id,
            status__in=[Subscription.Status.ACTIVE, Subscription.Status.TRIAL],
            start_date__lte=now,
        )
        .filter(Q(end_date__isnull=True) | Q(end_date__gt=now))
        .order_by("-start_date")
        .first()
    )
    hours = None
    if sub and isinstance(sub.configuration, dict):
        hours = sub.configuration.get("session_duration_hours")
    try:
        hours_int = int(hours)
    except Exception:
        raise CustomError(code=SESSION_EXPIRED, detail="Missing session_duration_hours in subscription config.", status_code=400)
    return max(1, min(24, hours_int))


def _max_concurrent_sessions_for_user(user) -> int:
    """Resolve max concurrent sessions for the user based on active org subscriptions (no env fallback)."""
    if not user or not getattr(user, "id", None):
        return 0
    now = timezone.now()
    org_ids = list(
        UserOrganization.objects.filter(user=user, is_active=True, deleted_at__isnull=True).values_list(
            "organization_id", flat=True
        )
    )
    if not org_ids:
        return 0
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
    for cfg in subs:
        if isinstance(cfg, dict) and cfg.get("max_concurrent_sessions") is not None:
            try:
                limits.append(int(cfg.get("max_concurrent_sessions")))
            except Exception:
                continue
    if limits:
        limit = min([l for l in limits if l >= 0])
    else:
        limit = 0
    return max(0, min(10, limit))


class SessionTokenObtainPairSerializer(TokenObtainPairSerializer):
    default_error_messages = {
        "no_active_account": {"code": INVALID_CREDENTIALS, "message": "Invalid email or password."}
    }

    def _evict_if_needed(self, user):
        max_sessions = _max_concurrent_sessions_for_user(user)
        if max_sessions <= 0:
            return
        active_sessions = list(
            AuthSession.objects.active().filter(user=user).order_by("created_at")
        )
        if len(active_sessions) < max_sessions:
            return
        oldest = active_sessions[0]
        oldest.deactivate(reason="concurrent_session_eviction")

    def validate(self, attrs):
        data = super().validate(attrs)
        request = self.context.get("request")

        refresh: RefreshToken = self.get_token(self.user)
        access = refresh.access_token

        # Attach default organization context if any
        active_membership = (
            UserOrganization.objects.filter(user=self.user, is_active=True, deleted_at__isnull=True)
            .values_list("organization_id", flat=True)
            .first()
        )

        if active_membership:
            access["active_organization_id"] = active_membership
            refresh["active_organization_id"] = active_membership
            hours = _session_duration_hours(active_membership)
        elif self.user.is_superuser:
            # Superusers may log in without org membership; fall back to default session duration.
            hours = getattr(settings, "AUTH_SESSION_DURATION_DEFAULT_HOURS", 24) or 24
        else:
            raise CustomError(
                code=SESSION_EXPIRED,
                detail="Organization context required for session duration.",
                status_code=400,
            )

        # Adjust refresh lifetime based on resolved session duration
        refresh.set_exp(lifetime=timedelta(hours=hours))
        ip = _client_ip(request)
        ua = _user_agent(request)

        self._evict_if_needed(self.user)

        session = AuthSession.objects.create(
            user=self.user,
            access_jti=access["jti"],
            refresh_jti=refresh["jti"],
            access_expires_at=_dt_from_timestamp(access["exp"]),
            ip_address=ip,
            user_agent=ua,
        )

        data.update(
            {
                "access": str(access),
                "refresh": str(refresh),
                "session_id": str(session.id),
            }
        )
        return data


class SessionTokenRefreshSerializer(TokenRefreshSerializer):
    default_error_messages = {
        "token_not_valid": {"code": SESSION_EXPIRED, "message": "Session expired or invalid."}
    }

    def validate(self, attrs):
        try:
            data = super().validate(attrs)
        except Exception:
            # Attempt to mark session as deactivated when refresh is invalid/expired
            try:
                refresh = RefreshToken(attrs.get("refresh"))
                jti = refresh.get("jti")
                user_id = refresh.get("user_id")
                if jti and user_id:
                    AuthSession.objects.filter(
                        refresh_jti=jti,
                        user_id=user_id,
                        deactivated_at__isnull=True,
                    ).update(deactivated_at=timezone.now(), deactivated_reason="refresh_invalid_or_expired")
            except Exception:
                pass
            raise

        refresh = RefreshToken(attrs["refresh"])
        user_id = refresh.get("user_id")
        jti = refresh.get("jti")
        if not jti or not user_id:
            raise CustomError(code=SESSION_EXPIRED, detail="Refresh token missing claims.", status_code=401)

        try:
            session = AuthSession.objects.active().get(refresh_jti=jti, user_id=user_id)
        except AuthSession.DoesNotExist:
            raise CustomError(code=SESSION_EXPIRED, detail="Session expired or revoked.", status_code=401)

        access = refresh.access_token
        session.mark_new_access(
            access_jti=access["jti"],
            access_expires_at=_dt_from_timestamp(access["exp"]),
        )
        session.touch()
        data["access"] = str(access)
        data["session_id"] = str(session.id)
        return data


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(required=True)

    def save(self, **kwargs):
        refresh_token = RefreshToken(self.validated_data["refresh"])
        jti = refresh_token.get("jti")
        user_id = refresh_token.get("user_id")
        if not jti or not user_id:
            raise CustomError(code=SESSION_EXPIRED, detail="Invalid refresh token.", status_code=401)
        qs = AuthSession.objects.filter(refresh_jti=jti, user_id=user_id, deactivated_at__isnull=True)
        updated = qs.update(deactivated_at=timezone.now(), deactivated_reason="logout")
        if not updated:
            raise CustomError(code=SESSION_REVOKED, detail="Session already revoked.", status_code=400)
        return True


class ContextSwitchSerializer(serializers.Serializer):
    organization_id = serializers.IntegerField(required=True, min_value=1)

    def validate(self, attrs):
        user = self.context["request"].user
        org_id = attrs["organization_id"]
        membership = UserOrganization.objects.filter(
            user=user, organization_id=org_id, deleted_at__isnull=True, is_active=True
        ).first()
        if not membership:
            raise CustomError(
                code=SESSION_REVOKED,
                detail="User is not an active member of this organization.",
                status_code=403,
            )
        attrs["membership"] = membership
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def save(self, **kwargs):
        email = self.validated_data["email"].lower()
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        token_generator = PasswordResetTokenGenerator()
        # Always respond success to avoid user enumeration
        if not user:
            return {"sent": True}
        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        token = token_generator.make_token(user)
        # Build reset link (for Mailpit/testing)
        domain = getattr(settings, "PLATFORM_URL", "localhost")
        scheme = "https" if getattr(settings, "SECURED_PLATFORM", False) else "http"
        path = reverse("password_reset_confirm")
        reset_link = f"{scheme}://{domain}{path}?uid={uidb64}&token={token}"
        try:
            send_mail(
                subject="Password reset",
                message=f"Use this link to reset your password: {reset_link}",
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@hudhud.local"),
                recipient_list=[user.email],
                fail_silently=True,
            )
        except Exception:
            # still return success; email delivery failures won't leak existence
            pass
        return {"sent": True, "uid": uidb64, "token": token, "reset_link": reset_link}


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        uidb64 = attrs["uid"]
        token = attrs["token"]
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid, is_active=True)
        except Exception:
            raise CustomError(code=SESSION_EXPIRED, detail="Invalid reset token.", status_code=400)

        token_generator = PasswordResetTokenGenerator()
        if not token_generator.check_token(user, token):
            raise CustomError(code=SESSION_EXPIRED, detail="Reset token expired or invalid.", status_code=400)

        attrs["user"] = user
        return attrs

    def validate_new_password(self, value):
        user = self.context.get("user")
        # run configured validators
        from django.contrib.auth.password_validation import validate_password

        try:
            validate_password(value, user=user)
        except Exception as exc:
            raise CustomError(code=PASSWORD_POLICY_VIOLATION, detail=str(exc), status_code=400)
        return value

    def save(self, **kwargs):
        user = self.validated_data["user"]
        new_password = self.validated_data["new_password"]
        user.set_password(new_password)
        user.save(update_fields=["password", "updated_at"])
        return True
