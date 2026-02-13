from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Any, Optional
import hashlib

from django.conf import settings
from django.utils import timezone
from django.core.mail import send_mail
from django.urls import reverse
from django.core.validators import validate_ipv46_address
from django.core.exceptions import ValidationError as DjangoValidationError
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
from django.contrib.auth import get_user_model

User = get_user_model()


def _client_ip(request) -> str | None:
    if not request:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    ip_candidate = None
    if forwarded:
        ip_candidate = forwarded.split(",", 1)[0].strip()
    else:
        ip_candidate = request.META.get("REMOTE_ADDR")
    if not ip_candidate:
        return None
    try:
        validate_ipv46_address(ip_candidate)
    except DjangoValidationError as exc:
        # Best-effort: ignore invalid IP rather than blocking login
        return None
    return ip_candidate


def _user_agent(request) -> str:
    if not request:
        return ""
    import re

    ua = request.META.get("HTTP_USER_AGENT", "") or ""
    # Remove script tags / javascript URLs / alert fragments.
    ua = re.sub(r"<\s*/?\s*script[^>]*>", "", ua, flags=re.IGNORECASE)
    ua = re.sub(r"javascript\s*:", "", ua, flags=re.IGNORECASE)
    ua = re.sub(r"alert\s*\(", "", ua, flags=re.IGNORECASE)
    # Strip angle brackets to avoid HTML injection.
    ua = ua.replace("<", "").replace(">", "")
    return ua[:500]


def _dt_from_timestamp(ts: Any) -> datetime:
    return datetime.fromtimestamp(int(ts), tz=dt_timezone.utc)


def _hash_refresh(refresh: str) -> str:
    return hashlib.sha256(refresh.encode("utf-8")).hexdigest()


def _session_duration_hours(org_id: Optional[int]) -> int:
    """Resolve session duration (refresh lifetime) from settings default (subscription override removed)."""
    hours = getattr(settings, "AUTH_SESSION_DURATION_DEFAULT_HOURS", 24) or 24
    return max(1, min(24, int(hours)))


def _max_concurrent_sessions_for_user(user) -> int:
    """Resolve max concurrent sessions from settings default (subscription override removed)."""
    limit = getattr(settings, "AUTH_MAX_CONCURRENT_SESSIONS", 5) or 5
    return max(0, int(limit))


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
        # Explicitly block inactive/deleted users
        if not getattr(self.user, "is_active", True) or getattr(self.user, "deleted_at", None):
            raise CustomError(
                code=INVALID_CREDENTIALS,
                detail="Invalid email or password.",
                status_code=400,
            )
        request = self.context.get("request")
        refresh: RefreshToken = self.get_token(self.user)
        refresh_str = str(refresh)
        refresh_hash = _hash_refresh(refresh_str)
        access = refresh.access_token
        access.set_exp(lifetime=timedelta(minutes=60))

        hours = _session_duration_hours(None)

        # Adjust refresh lifetime based on resolved session duration
        refresh.set_exp(lifetime=timedelta(hours=hours))
        ip = _client_ip(request)
        ua = _user_agent(request)

        self._evict_if_needed(self.user)

        session = AuthSession.objects.create(
            user=self.user,
            token_jti=access["jti"],
            refresh_token_hash=refresh_hash,
            access_expires_at=_dt_from_timestamp(access["exp"]),
            ip_address=ip,
            user_agent=ua,
        )

        data.update(
            {
                "access": str(access),
                "refresh": refresh_str,
                "session_id": str(session.id),
            }
        )
        return data


class SessionTokenRefreshSerializer(TokenRefreshSerializer):
    default_error_messages = {
        "token_not_valid": {"code": SESSION_EXPIRED, "message": "Session expired or invalid."}
    }

    def validate(self, attrs):
        refresh_str = attrs.get("refresh")
        refresh_hash = _hash_refresh(refresh_str or "")
        try:
            data = super().validate(attrs)
        except Exception:
            # Attempt to mark session as deactivated when refresh is invalid/expired
            try:
                refresh = RefreshToken(refresh_str or "")
                user_id = refresh.get("user_id")
                if user_id:
                    AuthSession.objects.filter(
                        refresh_token_hash=refresh_hash,
                        user_id=user_id,
                        deactivated_at__isnull=True,
                    ).update(deactivated_at=timezone.now(), deactivated_reason="refresh_invalid_or_expired")
            except Exception:
                pass
            raise

        try:
            refresh = RefreshToken(refresh_str or "")
        except Exception:
            raise CustomError(code=SESSION_EXPIRED, detail="Session expired or invalid.", status_code=401)
        user_id = refresh.get("user_id")
        # ensure user still active
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            user_obj = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            raise CustomError(code=SESSION_EXPIRED, detail="Session expired or revoked.", status_code=401)
        if not user_obj.is_active or getattr(user_obj, "deleted_at", None):
            raise CustomError(code=SESSION_EXPIRED, detail="Session expired or revoked.", status_code=401)
        if not user_id:
            raise CustomError(code=SESSION_EXPIRED, detail="Refresh token missing claims.", status_code=401)

        qs = AuthSession.objects.active().filter(refresh_token_hash=refresh_hash, user_id=user_id)
        if not qs.exists():
            raise CustomError(code=SESSION_EXPIRED, detail="Session expired or revoked.", status_code=401)

        # Invalidate existing access sessions for this refresh, then create a new one for the new access token
        qs.update(deactivated_at=timezone.now(), deactivated_reason="refresh_rotation")

        access = refresh.access_token
        access.set_exp(lifetime=timedelta(minutes=60))
        request = self.context.get("request")
        ip = _client_ip(request)
        ua = _user_agent(request)
        session = AuthSession.objects.create(
            user_id=user_id,
            token_jti=access["jti"],
            refresh_token_hash=_hash_refresh(str(refresh)),
            access_expires_at=_dt_from_timestamp(access["exp"]),
            ip_address=ip,
            user_agent=ua,
        )
        data["access"] = str(access)
        data["session_id"] = str(session.id)
        return data


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(required=True)

    def save(self, **kwargs):
        try:
            refresh_token = RefreshToken(self.validated_data["refresh"])
        except Exception:
            raise CustomError(code=SESSION_EXPIRED, detail="Invalid refresh token.", status_code=401)
        user_id = refresh_token.get("user_id")
        if not user_id:
            raise CustomError(code=SESSION_EXPIRED, detail="Invalid refresh token.", status_code=401)
        refresh_hash = _hash_refresh(str(refresh_token))
        qs = AuthSession.objects.filter(refresh_token_hash=refresh_hash, user_id=user_id, deactivated_at__isnull=True)
        if not qs.exists():
            raise CustomError(code=SESSION_REVOKED, detail="Session already revoked.", status_code=400)
        access_jti = qs.first().token_jti if qs.exists() else ""
        qs.update(deactivated_at=timezone.now(), deactivated_reason="logout")
        return {"access_jti": access_jti}


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
        # Deactivate all active sessions on password reset
        AuthSession.objects.filter(user=user, deactivated_at__isnull=True).update(
            deactivated_at=timezone.now(), deactivated_reason="password_reset"
        )
        return True

