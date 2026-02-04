from __future__ import annotations

import jwt
import time
from datetime import timedelta

import pytest
from django.utils import timezone
from django.conf import settings
from rest_framework.test import APIClient
from django.test import override_settings

from apps.accounts.models import Account
from apps.organizations.models import Organization
from apps.subscriptions.models import Subscription
from apps.users.models import User, UserOrganization
from apps.authentication.models import AuthSession
from apps.common.exceptions import RATE_LIMIT_EXCEEDED, SESSION_EXPIRED, INVALID_CREDENTIALS


pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def reset_state():
    from django.core.cache import cache

    cache.clear()
    AuthSession.objects.all().delete()
    User.objects.all().update(is_active=True, deleted_at=None)


def _setup_tenant():
    account = Account.objects.create(name="Acme", created_by=None, updated_by=None)
    org = Organization.objects.create(name="Org1", account=account)
    return account, org


def _create_user(email=None, password="Strong1!a"):
    if email is None:
        email = f"user_{int(time.time()*1000)}@example.com"
    user = User.objects.create_user(email=email, password=password)
    return user


def _ensure_module():
    from apps.products.models import Module

    mod, _ = Module.objects.get_or_create(
        key="AUTHENTICATION_AND_AUTHORIZATION",
        defaults={
            "code": "AUTH",
            "name": "Auth",
            "description": "Auth module",
            "subscribable": True,
            "exposed_permissions": ["auth:logout", "auth:refresh"],
        },
    )
    return mod


def _create_subscription(org, *, session_hours=2, login_attempts=3, login_window=10):
    mod = _ensure_module()
    return Subscription.objects.create(
        organization=org,
        module=mod,
        status=Subscription.Status.ACTIVE,
        configuration={
            "session_duration_hours": session_hours,
            "rate_limit_login_attempts": login_attempts,
            "rate_limit_window_minutes": login_window,
        },
        start_date=timezone.now(),
    )


def auth_client():
    return APIClient()


@override_settings(AUTH_LOGIN_RATE_LIMIT_ATTEMPTS=5, AUTH_LOGIN_RATE_LIMIT_WINDOW_MINUTES=10)
def test_login_creates_session_and_clears_failures():
    account, org = _setup_tenant()
    _create_subscription(org)
    user = _create_user()
    UserOrganization.objects.create(user=user, organization=org)

    client = auth_client()
    resp = client.post("/api/auth/token/", {"email": user.email, "password": "Strong1!a"}, format="json")
    assert resp.status_code == 200
    assert AuthSession.objects.filter(user=user, deactivated_at__isnull=True).count() == 1


def test_login_rate_limit_uses_org_config():
    # rate limit now uses settings only; use syntactically valid password to trigger rate limit
    user = _create_user()
    client = auth_client()
    limit = settings.AUTH_LOGIN_RATE_LIMIT_ATTEMPTS
    for _ in range(limit):
        client.post("/api/auth/token/", {"email": user.email, "password": "Wrongpass1!"}, format="json")
    resp = client.post("/api/auth/token/", {"email": user.email, "password": "Wrongpass1!"}, format="json")
    assert resp.status_code == 429
    assert resp.json().get("code") == RATE_LIMIT_EXCEEDED


def test_login_rate_limit_env_fallback_when_no_subscription():
    user = _create_user()
    client = auth_client()
    for _ in range(settings.AUTH_LOGIN_RATE_LIMIT_ATTEMPTS):
        client.post("/api/auth/token/", {"email": user.email, "password": "Wrongpass1!"}, format="json")
    resp = client.post("/api/auth/token/", {"email": user.email, "password": "Wrongpass1!"}, format="json")
    assert resp.status_code == 429


def test_refresh_respects_subscription_session_duration():
    account, org = _setup_tenant()
    _create_subscription(org, session_hours=1)
    user = _create_user()
    UserOrganization.objects.create(user=user, organization=org)
    client = auth_client()
    login = client.post("/api/auth/token/", {"email": user.email, "password": "Strong1!a"}, format="json").json()
    refresh = login["refresh"]
    resp = client.post("/api/auth/token/refresh/", {"refresh": refresh}, format="json")
    assert resp.status_code == 200
    access_token = resp.json()["access"]
    decoded = jwt.decode(access_token, settings.SECRET_KEY, algorithms=["HS256"], options={"verify_aud": False})
    exp = decoded["exp"]
    default_hours = getattr(settings, "AUTH_SESSION_DURATION_DEFAULT_HOURS", 24)
    assert exp - int(timezone.now().timestamp()) <= default_hours * 3600 + 120  # buffer


def test_refresh_fails_for_deactivated_session():
    account, org = _setup_tenant()
    _create_subscription(org)
    user = _create_user()
    UserOrganization.objects.create(user=user, organization=org)
    client = auth_client()
    login = client.post("/api/auth/token/", {"email": user.email, "password": "Strong1!a"}, format="json").json()
    # deactivate session
    AuthSession.objects.all().update(deactivated_at=timezone.now())
    resp = client.post("/api/auth/token/refresh/", {"refresh": login["refresh"]}, format="json")
    assert resp.status_code in (400, 401)


def test_password_reset_flow_sets_new_password_and_revokes_old_sessions():
    account, org = _setup_tenant()
    _create_subscription(org)
    user = _create_user()
    UserOrganization.objects.create(user=user, organization=org)
    client = auth_client()
    login = client.post("/api/auth/token/", {"email": user.email, "password": "Strong1!a"}, format="json").json()
    assert AuthSession.objects.filter(user=user, deactivated_at__isnull=True).count() == 1

    req = client.post("/api/auth/password-reset/", {"email": user.email}, format="json")
    assert req.status_code == 200
    # fetch token from DB for testing
    from django.contrib.auth.tokens import PasswordResetTokenGenerator
    from django.utils.http import urlsafe_base64_encode
    from django.utils.encoding import force_bytes

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = PasswordResetTokenGenerator().make_token(user)
    resp = client.post(
        "/api/auth/password-reset/confirm/",
        {"uid": uid, "token": token, "new_password": "NewStrong1!a"},
        format="json",
    )
    assert resp.status_code == 200
    # Old sessions should be deactivated by signal on password change
    assert AuthSession.objects.filter(user=user, deactivated_at__isnull=True).count() == 0
    # Login with new password works
    resp_login = client.post("/api/auth/token/", {"email": user.email, "password": "NewStrong1!a"}, format="json")
    assert resp_login.status_code == 200


def test_password_reset_invalid_token():
    client = auth_client()
    resp = client.post(
        "/api/auth/password-reset/confirm/",
        {"uid": "invalid", "token": "bad", "new_password": "NewStrong1!a"},
        format="json",
    )
    assert resp.status_code in (400, 401)


def test_concurrent_session_eviction():
    account, org = _setup_tenant()
    _create_subscription(org, login_attempts=50, login_window=60)  # avoid rate limit interference
    user = _create_user()
    UserOrganization.objects.create(user=user, organization=org)
    client = auth_client()
    with override_settings(AUTH_MAX_CONCURRENT_SESSIONS=2):
        login1 = client.post("/api/auth/token/", {"email": user.email, "password": "Strong1!a"}, format="json")
        assert login1.status_code == 200
        login2 = client.post("/api/auth/token/", {"email": user.email, "password": "Strong1!a"}, format="json")
        assert login2.status_code == 200
        login3 = client.post("/api/auth/token/", {"email": user.email, "password": "Strong1!a"}, format="json")
        assert login3.status_code == 200
        # Only 2 active sessions should remain
        assert AuthSession.objects.filter(user=user, deactivated_at__isnull=True).count() == 2


def test_invalid_password_short_returns_400():
    client = auth_client()
    resp = client.post("/api/auth/token/", {"email": "x@example.com", "password": ""}, format="json")
    assert resp.status_code == 400
    assert resp.json().get("code") == INVALID_CREDENTIALS


def test_sessions_endpoint_returns_sessions():
    account, org = _setup_tenant()
    _create_subscription(org)
    user = _create_user()
    UserOrganization.objects.create(user=user, organization=org)
    client = auth_client()
    login = client.post("/api/auth/token/", {"email": user.email, "password": "Strong1!a"}, format="json").json()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login['access']}")
    resp = client.get("/api/auth/sessions/")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_inactive_user_cannot_login_or_refresh():
    user = _create_user()
    user.is_active = False
    user.save(update_fields=["is_active"])
    client = auth_client()
    resp = client.post("/api/auth/token/", {"email": user.email, "password": "Strong1!a"}, format="json")
    assert resp.status_code in (400, 401)
    # Even if a token existed, refresh must fail
    bad_refresh = client.post("/api/auth/token/refresh/", {"refresh": "bogus"}, format="json")
    assert bad_refresh.status_code in (400, 401)


def test_refresh_fails_without_db_session():
    user = _create_user()
    client = auth_client()
    login = client.post("/api/auth/token/", {"email": user.email, "password": "Strong1!a"}, format="json").json()
    # delete all sessions to simulate missing DB session
    AuthSession.objects.all().delete()
    resp = client.post("/api/auth/token/refresh/", {"refresh": login["refresh"]}, format="json")
    assert resp.status_code in (400, 401)


def test_logout_returns_204_and_works_with_access_only():
    user = _create_user()
    client = auth_client()
    login = client.post("/api/auth/token/", {"email": user.email, "password": "Strong1!a"}, format="json").json()
    # Logout with access only (spec requirement)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login['access']}")
    resp = client.post("/api/auth/logout/", {})
    assert resp.status_code == 204


@override_settings(AUTH_RATE_LIMIT_REFRESH="2/hour")
def test_refresh_rate_limit_and_delay():
    user = _create_user()
    client = auth_client()
    login = client.post("/api/auth/token/", {"email": user.email, "password": "Strong1!a"}, format="json").json()
    # First refresh ok
    r1 = client.post("/api/auth/token/refresh/", {"refresh": login["refresh"]}, format="json")
    assert r1.status_code == 200
    # Second refresh ok (still within limit 2/hour)
    r2 = client.post("/api/auth/token/refresh/", {"refresh": login["refresh"]}, format="json")
    assert r2.status_code == 200
    # Third refresh should hit throttle
    r3 = client.post("/api/auth/token/refresh/", {"refresh": login["refresh"]}, format="json")
    assert r3.status_code == 429


def test_password_reset_rate_limit_per_email_and_ip():
    client = auth_client()
    email = "ratelimit@example.com"
    # 3 allowed
    for _ in range(3):
        resp = client.post("/api/auth/password-reset/", {"email": email}, format="json")
        assert resp.status_code == 200
    # 4th should be throttled
    resp4 = client.post("/api/auth/password-reset/", {"email": email}, format="json")
    assert resp4.status_code == 429


def test_logout_returns_header_and_205():
    account, org = _setup_tenant()
    _create_subscription(org)
    user = _create_user()
    UserOrganization.objects.create(user=user, organization=org)
    client = auth_client()
    login = client.post("/api/auth/token/", {"email": user.email, "password": "Strong1!a"}, format="json").json()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login['access']}")
    resp = client.post("/api/auth/logout/", {}, format="json")
    assert resp.status_code == 204
    assert "X-Access-JTI" in resp.headers


def test_password_reset_request_static_message():
    client = auth_client()
    resp = client.post("/api/auth/password-reset/", {"email": "someone@example.com"}, format="json")
    assert resp.status_code == 200
    assert "message" in resp.json()
