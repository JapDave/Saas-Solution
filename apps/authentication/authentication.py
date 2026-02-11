from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.authentication.models import AuthSession
SESSION_EXPIRED = "SESSION_EXPIRED"
SESSION_REVOKED = "SESSION_REVOKED"


class SessionJWTAuthentication(JWTAuthentication):
    """
    JWT auth that enforces DB-backed session validity and inactivity window.
    """

    www_authenticate_realm = "api"

    def authenticate(self, request):
        res = super().authenticate(request)
        if not res:
            return None
        user, validated_token = res
        jti = validated_token.get("jti")
        if not jti:
            raise AuthenticationFailed(
                {"code": SESSION_EXPIRED, "message": "Token missing JTI claim."},
                code=SESSION_EXPIRED,
            )
        try:
            session = AuthSession.objects.active().get(user=user, token_jti=jti)
        except AuthSession.DoesNotExist:
            raise AuthenticationFailed(
                {"code": SESSION_EXPIRED, "message": "Session not active or expired."},
                code=SESSION_EXPIRED,
            )

        # Inactivity timeout
        inactivity_minutes = getattr(settings, "AUTH_SESSION_INACTIVITY_MINUTES", 60) or 60
        if session.last_activity_at and session.last_activity_at < timezone.now() - timedelta(minutes=inactivity_minutes):
            session.deactivate(reason="inactivity_timeout")
            raise AuthenticationFailed(
                {"code": SESSION_REVOKED, "message": "Session expired due to inactivity."},
                code=SESSION_REVOKED,
            )

        # Touch last activity (best-effort)
        try:
            session.touch()
        except Exception:
            pass

        # Attach for downstream (authorization/audit)
        request.auth_session = session
        return user, validated_token
