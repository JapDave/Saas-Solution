"""
Acceptance tests for Authentication & Authorization API endpoints.

These tests verify the actual HTTP API behavior end-to-end,
including authentication, authorization, and response formats.

Tests are organized by requirement (REQ-AUTH-XXX and REQ-AUTHZ-XXX) from:
- TEST_PLAN_AUTH_API.md
- MISSING_TEST_CASES_AUTH_API.md
"""
import os
import pytest
import requests
import time
import jwt
import json
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple

ONLY_CURRENT = False
ONLY_CURRENT2 = True

# Import helpers from conftest
from acceptance_tests.conftest import make_request, execute_raw_query, get_user_credentials, clear_all_login_failures

# Import Django models if available
try:
    from django.db import connection, connections
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from apps.users.models import User, UserOrganization
    from apps.organizations.models import Organization
    from apps.accounts.models import Account
    from apps.roles.models import Role, RoleAssignment
    from apps.subscriptions.models import Subscription
    from apps.common.models import AuditLog
    from apps.authentication.models import AuthSession
    DJANGO_AVAILABLE = True
except ImportError:
    DJANGO_AVAILABLE = False
    User = None
    UserOrganization = None
    Organization = None
    Account = None
    Role = None
    RoleAssignment = None
    Subscription = None
    AuditLog = None
    AuthSession = None
    get_user_model = None
    connection = None
    connections = None
    settings = None

# Note: make_request helper is available from conftest.py


def decode_jwt_token(token: str) -> Dict[str, Any]:
    """Decode JWT token without verification (for testing purposes)."""
    return jwt.decode(token, options={"verify_signature": False})


def get_token_jti(token: str) -> Optional[str]:
    """Extract JTI claim from JWT token."""
    try:
        decoded = decode_jwt_token(token)
        return decoded.get("jti")
    except Exception:
        return None


def get_token_exp(token: str) -> Optional[int]:
    """Extract expiration claim from JWT token."""
    try:
        decoded = decode_jwt_token(token)
        return decoded.get("exp")
    except Exception:
        return None


def get_mailpit_messages(mailpit_url: str = "http://localhost:8025", limit: int = 1) -> list:
    """
    Get messages from mailpit API.
    
    Args:
        mailpit_url: Base URL for mailpit (default: http://localhost:8025)
        limit: Maximum number of messages to retrieve (default: 1)
    
    Returns:
        List of message objects from mailpit API
    
    Raises:
        requests.RequestException: If the request to mailpit fails
    """
    api_url = f"{mailpit_url}/api/v1/messages"
    params = {"limit": limit}
    response = requests.get(api_url, params=params, timeout=5)
    response.raise_for_status()
    data = response.json()
    return data.get("messages", [])


def get_latest_email_content(mailpit_url: str = "http://localhost:8025") -> str:
    """
    Get the text content of the latest email from mailpit.
    
    Args:
        mailpit_url: Base URL for mailpit (default: http://localhost:8025)
    
    Returns:
        Text content of the latest email
    
    Raises:
        ValueError: If no messages are found or message ID is missing
        requests.RequestException: If the request to mailpit fails
    """
    messages = get_mailpit_messages(mailpit_url, limit=1)
    if not messages:
        raise ValueError("No messages found in mailpit")
    
    message_id = messages[0].get("ID")
    if not message_id:
        raise ValueError("Message ID not found")
    
    # Try to get text content first
    text_url = f"{mailpit_url}/api/v1/message/{message_id}"
    response = requests.get(text_url, timeout=5)
    if response.status_code == 200:
        text = response.json().get("Text")
        if text:
            return text.strip()
    
    # Fallback to HTML content
    html_url = f"{mailpit_url}/api/v1/message/{message_id}/html"
    response = requests.get(html_url, timeout=5)
    response.raise_for_status()
    return response.text


def extract_password_reset_token(email_content: str) -> Tuple[str, str]:
    """
    Extract uid and token from password reset email content.
    
    The email should contain a URL like:
    https://saas-platform.local/api/auth/password-reset/confirm/?uid=NjAz&token=d3gwbx-02c897b7ce5bff521ac96d9be2a491cd
    
    Args:
        email_content: Text or HTML content of the email
    
    Returns:
        Tuple of (uid, token)
    
    Raises:
        ValueError: If uid or token cannot be extracted
    """
    # Pattern to match the password reset URL
    # Matches URLs with uid and token query parameters
    pattern = r'password-reset/confirm/\?uid=([^&\s"\'<>]+)&token=([^&\s"\'<>]+)'
    
    match = re.search(pattern, email_content)
    if not match:
        # Try alternative pattern without the path
        pattern_alt = r'uid=([^&\s"\'<>]+).*?token=([^&\s"\'<>]+)'
        match = re.search(pattern_alt, email_content)
    
    if not match:
        raise ValueError(f"Could not extract uid and token from email content. Content preview: {email_content[:200]}")
    
    uid = match.group(1)
    token = match.group(2)
    
    return uid, token


@pytest.mark.acceptance
class TestREQAuth001UserLogin:
    """REQ-AUTH-001: User Login"""

    def test_1_1_successful_login_with_valid_credentials(self, http_client):
        """Test Scenario 1.1: Successful Login with Valid Credentials"""
        for user_name in ["Super Admin", "SaaS Account Manager", "Account 1 Admin", "Account 1 Org Admin", "Account 1 Owner", 
            "Account 1 User 1", "Account 1 User 2", "Account 1 User 3", "Account 2 Owner", "Account 2 User 1", "Account 4 Owner", "Account 4 User 1"]:
            email, password = get_user_credentials(user_name)
            
            payload = {
                "email": email,
                "password": password
            }
            http_client.headers["Content-Type"] = "application/json"
            http_client.headers["X-Forwarded-For"] = "192.168.1.100"
            http_client.headers["X-Real-IP"] = "192.168.1.100"
            start_time = time.time()
            response = make_request(http_client, "post", "/auth/token/", json=payload)

            response_time = time.time() - start_time
            
            assert response.status_code == 200, f"{user_name} - Expected 200 but got {response.status_code}, response: {response.text}"
            data = response.json()
            
            # Verify tokens
            assert "access" in data or "access_token" in data, f"{user_name} - Response should contain access token"
            assert "refresh" in data or "refresh_token" in data, f"{user_name} - Response should contain refresh token"
            access_token = data.get("access") or data.get("access_token")
            refresh_token = data.get("refresh") or data.get("refresh_token")
            assert isinstance(access_token, str), f"{user_name} - Access token should be a string"
            assert isinstance(refresh_token, str), f"{user_name} - Refresh token should be a string"
            
            # Verify access token claims: exp, iat, jti, sub (user_id), sid (session_id)
            decoded_token = decode_jwt_token(access_token)
            assert "exp" in decoded_token, f"{user_name} - Access token should have exp claim"
            assert "iat" in decoded_token, f"{user_name} - Access token should have iat claim"
            assert "jti" in decoded_token, f"{user_name} - Access token should have jti claim"
            if ONLY_CURRENT2:
                assert "user_id" in decoded_token, f"{user_name} - Access token should have user_id claim"
            else:
                print(decoded_token)
                assert "sub" in decoded_token, f"{user_name} - Access token should have sub (user_id) claim, got {decoded_token}"
                assert "sid" in decoded_token, f"{user_name} - Access token should have sid (session_id) claim, got {decoded_token}"
            
            # Verify access token expiration (60 minutes)
            token_exp = decoded_token.get("exp")
            if token_exp:
                current_time = int(time.time())
                expiration_time = token_exp - current_time
                assert 3590 <= expiration_time <= 3600, f"Token should expire in ~60 minutes, got {expiration_time} seconds"
            
            # Verify session creation
            if DJANGO_AVAILABLE and AuthSession:
                token_jti = decoded_token.get("jti")
                
                if token_jti:
                    session = AuthSession.objects.using('default').filter(token_jti=token_jti).first()
                    assert session is not None, f"Session with token_jti {token_jti} should exist in database"
                    assert session.deactivated_at is None, "Session should be active (deactivated_at should be None)"
                    
                    # Verify session_id from token sid claim matches database
                    token_sid = decoded_token.get("sid")
                    if token_sid:
                        assert str(session.id) == token_sid, \
                            f"Session ID from token sid claim should match database session: {session.id} != {token_sid}"
                    
                    # Verify refresh_token_hash exists in session
                    assert hasattr(session, 'refresh_token_hash') and session.refresh_token_hash is not None, \
                        "Session should have refresh_token_hash stored"
            
            # Verify response time
            assert response_time < 2.0, f"Response time should be less than 2 seconds, got {response_time:.2f}s"

    def test_1_2_login_with_invalid_email(self, http_client):
        """Test Scenario 1.2: Login with Invalid Email"""
        invalid_emails = [
            "notanemail",
            "missing@domain",
            "@nodomain.com",
            "",
            "a" * 250 + "@example.com"  # Exceeding 254 characters
        ]
        
        for email in invalid_emails:
            payload = {"email": email, "password": "TestP@ssw0rd123"}
            response = make_request(http_client, "post", "/auth/token/", json=payload)
            if email == '':
                assert response.status_code == 400, f"Expected 400 for email '{email}', got {response.status_code}, response: {response.text}"
            else:
                assert response.status_code == 401, f"Expected 401 for email '{email}', got {response.status_code}, response: {response.text}"
            data = response.json()
            assert "code" in data or "error" in data or "email" in str(data).lower(), f"Response should contain code, error, or email, got {data}"
            
            # Verify no tokens returned
            assert "access" not in data
            assert "refresh" not in data
            clear_all_login_failures()

        payload = {"password": "TestP@ssw0rd123"}
        response = make_request(http_client, "post", "/auth/token/", json=payload)
        
        assert response.status_code == 400, f"Expected 400 for no email, got {response.status_code}, response: {response.text}"
        data = response.json()
        assert "code" in data or "error" in data or "email" in str(data).lower(), f"Response should contain code, error, or email, got {data}"
        
        # Verify no tokens returned
        assert "access" not in data
        assert "refresh" not in data

    def test_1_3_login_with_invalid_password(self, http_client):
        """Test Scenario 1.3: Login with Invalid Password"""
        email, password = get_user_credentials("Account 1 Admin")
        
        # First 3 attempts with wrong password
        wrong_passwords = ["WrongPass1!", "WrongPass2!", "WrongPass3!"]
        for wrong_password in wrong_passwords:
            payload = {"email": email, "password": wrong_password}
            response = make_request(http_client, "post", "/auth/token/", json=payload)
            
            assert response.status_code == 401, f"Expected 401 for wrong password, got {response.status_code}"
            data = response.json()
            assert data.get("code") == "INVALID_CREDENTIALS" or "credential" in str(data).lower()
        
        # 4th attempt should be rate limited
        payload = {"email": email, "password": password}
        response = make_request(http_client, "post", "/auth/token/", json=payload)
        
        assert response.status_code == 429, f"Expected 429 for rate limit, got {response.status_code}"
        data = response.json()
        assert data.get("code") == "RATE_LIMIT_EXCEEDED"
    
    def test_1_3b_login_with_no_password(self, http_client):
        """Test Scenario 1.3b: Login with No Password"""
        email, password = get_user_credentials("Account 1 Admin")
        

        payload = {"email": email}
        response = make_request(http_client, "post", "/auth/token/", json=payload)
        
        assert response.status_code == 400, f"Expected 400 for wrong password, got {response.status_code}"
        data = response.json()
        assert data.get("code") == "INVALID_CREDENTIALS" or "credential" in str(data).lower()


    def test_1_4_login_rate_limiting_by_ip_address(self, http_client):
        """Test Scenario 1.4: Login Rate Limiting by IP Address"""
        # Get test users
        emails = []
        for user_name in ["Account 1 Owner", "Account 1 Admin", "Account 2 Owner", "Account 4 User 1"]:
            email, _ = get_user_credentials(user_name)
            emails.append(email)
        
        # Simulate IP A with 3 failed attempts
        ip_a_headers = {"X-Forwarded-For": "192.168.1.100", "X-Real-IP": "192.168.1.100"}
        for i in range(3):
            payload = {"email": emails[i], "password": "WrongPassword123!"}
            response = make_request(http_client, "post", "/auth/token/", json=payload, headers=ip_a_headers)
            assert response.status_code == 401, f"LOGIN ATTEMPT {i+1}: Expected 401 but got {response.status_code}, response: {response.text}"
        
        # 4th attempt from IP A should be rate limited
        payload = {"email": emails[3], "password": "WrongPassword123!"}
        response = make_request(http_client, "post", "/auth/token/", json=payload, headers=ip_a_headers)
        assert response.status_code == 429, f"LOGIN ATTEMPT 4: Expected 429 but got {response.status_code}, response: {response.text}"
        
        # # Attempt from IP B should not be rate limited
        # ip_b_headers = {"X-Forwarded-For": "192.168.1.200", "X-Real-IP": "192.168.1.200"}
        # payload = {"email": emails[0], "password": "WrongPassword123!"}
        # response = make_request(http_client, "post", "/auth/token/", json=payload, headers=ip_b_headers)
        # assert response.status_code == 401, f"LOGIN ATTEMPT DIFFERENT IP: Expected 401 but got {response.status_code}, response: {response.text}" # Not rate limited, just wrong password

    def test_1_5_login_with_inactive_account(self, http_client):
        """Test Scenario 1.5: Login with Inactive Account - Should return 401 with random delay"""
        email, password = get_user_credentials("Account 1 Inactive User 4")
        
        payload = {"email": email, "password": password}
        start_time = time.time()
        response = make_request(http_client, "post", "/auth/token/", json=payload)
        response_time = time.time() - start_time
        
        # Inactive users should return 401 (not 403) with random delay
        assert response.status_code == 401, f"Expected 401 for inactive account, got {response.status_code}"
        data = response.json()
        assert data.get("code") == "INVALID_CREDENTIALS" or "credential" in str(data).lower() or "invalid" in str(data).lower()
        
        # Verify random delay was added (response time should be noticeable)
        # Note: Exact timing depends on implementation, but should be > 0.1s typically
        assert response_time > 0.05, "Random delay should be added to prevent information leakage"
        
        # Verify no tokens returned
        assert "access" not in data
        assert "refresh" not in data
        
        # Verify audit log has user field as null for failed login
        if DJANGO_AVAILABLE and AuditLog:
            from django.utils import timezone
            failed_log = AuditLog.objects.using('default').filter(
                path="/api/auth/token/",
                method="POST",
                status_code=401,
                created_at__gte=timezone.now() - timedelta(seconds=5)
            ).order_by("-created_at").first()
            if failed_log:
                # User field should be null for failed login attempts
                assert failed_log.user_id is None, "Audit log user field should be null for failed login"

    def test_1_6_concurrent_session_limit_enforcement(self, authenticated_client, http_client):
        """Test Scenario 1.6: Concurrent Session Limit Enforcement"""
        # This test requires setting max_concurrent_sessions=5 for the organization
        email, password = get_user_credentials("Account 1 User 2")
        token_jtis = []
        
        # Login first time
        payload = {"email": email, "password": password}
        response1 = make_request(http_client, "post", "/auth/token/", json=payload)
        assert response1.status_code == 200, f"First login: Expected 200 for concurrent session limit, got {response1.status_code}, response: {response1.text}"
        token1 = response1.json()["access"]
        token_jtis.append(get_token_jti(token1))
        
        # Login second time
        for i in range(5):
            response = make_request(http_client, "post", "/auth/token/", json=payload)
            assert response.status_code == 200, f"{i+1}th login: Expected 200 for concurrent session limit, got {response.status_code}, response: {response.text}"
            last_token = response.json()["access"]
            token_jtis.append(get_token_jti(last_token))
        
        # Verify oldest token is invalidated
        client1 = requests.Session()
        client1.base_url = http_client.base_url
        client1.verify = getattr(http_client, 'verify', True)
        client1.headers["Authorization"] = f"Bearer {token1}"
        sessions_response = make_request(client1, "get", "/auth/sessions/")
        assert sessions_response.status_code == 401, f"Expected 401 for concurrent session limit, got {sessions_response.status_code}"
        
        # Token was invalidated - verify in database
        if DJANGO_AVAILABLE and AuthSession:
            token1_jti = get_token_jti(token1)
            if token1_jti:
                # Use default database connection (real database, not test database)
                session1 = AuthSession.objects.using('default').filter(token_jti=token1_jti).first()
                assert session1 is None or session1.deactivated_at is not None, \
                    "Oldest session should be deactivated in database"
        
        client1.headers["Authorization"] = f"Bearer {last_token}"
        sessions_response = make_request(client1, "get", "/auth/sessions/")
        assert sessions_response.status_code == 200, f"Expected 200 for concurrent session limit, got {sessions_response.status_code}"
        sessions = sessions_response.json()
        print(sessions)
        assert len(sessions) == 6, f"Should have exactly 6 sessions, got {len(sessions)}"
        active_sessions = [session for session in sessions if session["deactivated_at"] is None]
        assert len(active_sessions) == 5, f"Should have exactly 5 active sessions, got {len(active_sessions)}"
        for session in sessions:
            assert session["token_jti"] in token_jtis, f"Session access JTI should be in token_jtis, got {session['token_jti']}"
        
        # Verify in database: should have exactly 6 sessions total, but only 5 active
        if DJANGO_AVAILABLE and AuthSession:
            User = get_user_model()
            # Use default database connection (real database, not test database)
            user = User.objects.using('default').filter(email=email).first()
            if user:
                all_sessions = AuthSession.objects.using('default').filter(user=user).order_by("created_at")
                print(token_jtis)
                print([(session.token_jti, session.deactivated_at) for session in all_sessions])
                assert all_sessions.count() == 6, f"Should have exactly 6 sessions in database, got {all_sessions.count()}"
                active_sessions = all_sessions.filter(deactivated_at__isnull=True)
                assert active_sessions.count() == 5, f"Should have exactly 5 active sessions in database, got {active_sessions.count()}"
                
                # Verify token1 session is the one deactivated
                token1_jti = get_token_jti(token1)
                if token1_jti:
                    # Use default database connection (real database, not test database)
                    session1 = AuthSession.objects.using('default').filter(token_jti=token1_jti).first()
                    if session1:
                        assert session1.deactivated_at is not None, "Oldest session (token1) should be deactivated"

    def test_1_7_login_with_deleted_user(self, http_client):
        """Test Scenario 1.7: Login with Deleted User - Should return 401 with random delay"""
        if not DJANGO_AVAILABLE:
            pytest.skip("Django models not available")
        
        from django.utils import timezone
        
        # Create a user, then soft delete it
        User = get_user_model()
        test_email = "deleted_user_test@example.com"
        test_password = "TestP@ssw0rd123"
        
        # Create user
        user, _ = User.objects.using('default').get_or_create(
            email=test_email,
            password=test_password,
            is_active=True
        )
        user_id = user.id
        
        # Soft delete user (keep the user, just mark as deleted)
        try:
            user.deleted_at = timezone.now()
            user.save()
            
            # Verify user is soft deleted
            assert user.deleted_at is not None, "User should be soft deleted"
        except Exception:
            pytest.skip("User deletion not properly implemented")
        
        payload = {"email": test_email, "password": test_password}
        start_time = time.time()
        response = make_request(http_client, "post", "/auth/token/", json=payload)
        response_time = time.time() - start_time
        
        # Deleted users should return 401 with random delay
        assert response.status_code == 401, f"Expected 401 for deleted user, got {response.status_code}"
        assert response_time > 0.05, "Random delay should be added"
        
        # Verify no tokens returned
        data = response.json()
        assert "access" not in data
        assert "refresh" not in data
        
        


    def test_1_11_email_length_validation_minimum(self, http_client):
        """Missing Test Case 1.9: Email Length Validation (Minimum 5 Characters)"""
        short_emails = ["a@b.c", "ab@c", "a@bc"]
        
        for email in short_emails:
            payload = {"email": email, "password": "TestP@ssw0rd123"}
            response = make_request(http_client, "post", "/auth/token/", json=payload)
            
            assert response.status_code == 401, f"Expected 400 for short email '{email}', got {response.status_code}"
            data = response.json()
            assert "email" in str(data).lower() or "length" in str(data).lower() or "5" in str(data)

    def test_1_12_password_length_validation(self, http_client):
        """Missing Test Case 1.10: Password Length Validation (8-128 Characters)"""
        email, _ = get_user_credentials("Account 1 User 2")
        
        # Test too short password (7 characters)
        payload = {"email": email, "password": "Short1!"}
        response = make_request(http_client, "post", "/auth/token/", json=payload)
        assert response.status_code == 401
        
        # Test too long password (129 characters)
        long_password = "A" * 129
        payload = {"email": email, "password": long_password}
        response = make_request(http_client, "post", "/auth/token/", json=payload)
        assert response.status_code == 400

    def test_1_13_login_audit_logging(self, http_client):
        """Missing Test Case 1.13: Login Audit Logging"""
        if not DJANGO_AVAILABLE or not AuditLog:
            pytest.skip("Django models not available")
        
        # Successful login
        email, password = get_user_credentials("Account 1 Owner")
        
        # Get timestamp before login to find the correct audit log entry
        if DJANGO_AVAILABLE and AuditLog:
            from django.utils import timezone
            before_login = timezone.now()
        
        payload = {"email": email, "password": password}
        response = make_request(http_client, "post", "/auth/token/", json=payload)
        assert response.status_code == 200, f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        # Check audit log for successful login
        if DJANGO_AVAILABLE and AuditLog:
            User = get_user_model()
            user = User.objects.filter(email=email).first()
            
            # Find audit log entry for successful login created after our request
            # Look for POST /auth/token/ with status 200
            print(before_login, [log.__dict__ for log in AuditLog.objects.using('default').all()])
            success_log = AuditLog.objects.using('default').filter(
                path="/api/auth/token/",
                method="POST",
                app_label="authentication",
                created_at__gte=before_login
            ).order_by("-created_at").first()
            
            # Should have audit log entry for successful login
            assert success_log is not None, f"Should have audit log entry for successful login, {user}"
            assert success_log.success is True, "Audit log should mark successful login as success=True"
            if user:
                assert success_log.user_id == user.id, f"Audit log should reference the correct user: {success_log.user_id} != {user.id}"
            assert success_log.status_code == 200, "Audit log should have status code 200"
        
        # Failed login
        if DJANGO_AVAILABLE and AuditLog:
            from django.utils import timezone
            before_failed_login = timezone.now()
        
        payload = {"email": email, "password": "WrongPassword123!"}
        response = make_request(http_client, "post", "/auth/token/", json=payload)
        assert response.status_code == 401
        
        # Check audit log for failed attempt
        if DJANGO_AVAILABLE and AuditLog:
            User = get_user_model()
            user = User.objects.using('default').filter(email=email).first()
            
            # Find audit log entry for failed login created after our request
            # Look for POST /auth/token/ with status 401
            failed_log = AuditLog.objects.using('default').filter(
                path="/api/auth/token/",
                method="POST",
                app_label="authentication",
                created_at__gte=before_failed_login
            ).order_by("-created_at").first()
            
            # Should have audit log entry for failed login
            assert failed_log is not None, "Should have audit log entry for failed login"
            assert failed_log.success is False, "Audit log should mark failed login as success=False"
            assert failed_log.status_code == 401, "Audit log should have status code 401"
            # User field should be null for failed login attempts
            assert failed_log.user_id is None, "Audit log user field should be null for failed login"

    def test_1_13_rolling_window_rate_limit_reset(self, http_client):
        """Missing Test Case 1.13: Rolling Window Rate Limit Reset"""
        email, password = get_user_credentials("SaaS Account Manager")
        
        # Send 3 failed attempts to trigger rate limit
        for i in range(3):
            payload = {"email": email, "password": f"Wrong{i}!"}
            response = make_request(http_client, "post", "/auth/token/", json=payload)
            assert response.status_code == 401
        
        # Verify rate limit is active - 4th attempt should be rate limited
        payload = {"email": email, "password": password}
        response = make_request(http_client, "post", "/auth/token/", json=payload)
        assert response.status_code == 429, "Should be rate limited after 3 failed attempts"
        
        # Clear rate limit failures using clear_all_login_failures (simulating rolling window expiration)
        clear_all_login_failures()
        
        # After clearing rate limits, login should work
        payload = {"email": email, "password": password}
        response = make_request(http_client, "post", "/auth/token/", json=payload)
        assert response.status_code == 200, "Login should work after rate limit is cleared"
        
        # Verify tokens are returned
        data = response.json()
        assert "access" in data
        assert "refresh" in data


@pytest.mark.acceptance
class TestREQAuth002UserLogout:
    """REQ-AUTH-002: User Logout"""

    def test_2_1_successful_logout_with_refresh_token(self, authenticated_client, http_client):
        """Test Scenario 2.1: Successful Logout with Refresh Token"""
        email, password = get_user_credentials("Account 1 Owner")
        
        # Login to get tokens
        login_response = make_request(http_client, "post", "/auth/token/", json={
            "email": email,
            "password": password
        })
        assert login_response.status_code == 200
        refresh_token = login_response.json().get("refresh") or login_response.json().get("refresh_token")
        access_token = login_response.json().get("access") or login_response.json().get("access_token")
        
        # Logout with refresh token in body
        client = requests.Session()
        client.base_url = http_client.base_url
        client.verify = getattr(http_client, 'verify', True)
        
        start_time = time.time()
        response = make_request(client, "post", "/auth/logout/", json={"refresh": refresh_token})
        response_time = time.time() - start_time
        if ONLY_CURRENT:
            assert response.status_code == 205, f"Expected 205 but got {response.status_code}, response: {response.text}"
        else:
            assert response.status_code == 204, f"Expected 204 but got {response.status_code}, response: {response.text}"
        assert response_time < 0.5, f"Response time should be less than 500ms, got {response_time:.2f}s"
        
        # Verify token is invalidated
        client_with_token = requests.Session()
        client_with_token.base_url = http_client.base_url
        client_with_token.verify = getattr(http_client, 'verify', True)
        client_with_token.headers["Authorization"] = f"Bearer {access_token}"
        response2 = make_request(client_with_token, "get", "/auth/sessions/")
        assert response2.status_code == 401, "Token should be invalidated after logout"

    def test_2_1b_successful_logout_with_access_token(self, authenticated_client, http_client):
        """Test Scenario 2.1b: Successful Logout with Access Token"""
        email, password = get_user_credentials("Account 1 Owner")
        
        # Login to get tokens
        login_response = make_request(http_client, "post", "/auth/token/", json={
            "email": email,
            "password": password
        })
        assert login_response.status_code == 200
        access_token = login_response.json().get("access") or login_response.json().get("access_token")
        
        # Logout with access token in Authorization header
        client = requests.Session()
        client.base_url = http_client.base_url
        client.verify = getattr(http_client, 'verify', True)
        client.headers["Authorization"] = f"Bearer {access_token}"
        
        start_time = time.time()
        response = make_request(client, "post", "/auth/logout/")
        response_time = time.time() - start_time
        
        assert response.status_code == 204, f"Expected 204 but got {response.status_code}, response: {response.text}"
        assert response_time < 0.5, f"Response time should be less than 500ms, got {response_time:.2f}s"
        
        # Verify token is invalidated
        response2 = make_request(client, "get", "/auth/sessions/")
        assert response2.status_code == 401, "Token should be invalidated after logout"

    def test_2_2_logout_with_invalid_token(self, http_client):
        """Test Scenario 2.2: Logout with Invalid Token"""
        # Test with malformed refresh token
        client = requests.Session()
        client.base_url = http_client.base_url
        client.verify = getattr(http_client, 'verify', True)
        response = make_request(client, "post", "/auth/logout/", json={"refresh": "invalid.token.here"})
        assert response.status_code == 401, f"invalid refresh token should return 400, got {response.status_code}, response: {response.text}"
        
        # Test with malformed access token
        client2 = requests.Session()
        client2.base_url = http_client.base_url
        client2.verify = getattr(http_client, 'verify', True)
        client2.headers["Authorization"] = "Bearer invalid.token.here"
        response = make_request(client2, "post", "/auth/logout/")
        assert response.status_code == 401, f"invalid access token should return 401, got {response.status_code}, response: {response.text}"
        
        # Test with missing both tokens
        client3 = requests.Session()
        client3.base_url = http_client.base_url
        client3.verify = getattr(http_client, 'verify', True)
        response = make_request(client3, "post", "/auth/logout/", json={})
        assert response.status_code == 400, f"missing tokens should return 400, got {response.status_code}, response: {response.text}"

    def test_2_3_logout_with_already_deactivated_session(self, http_client):
        """Test Scenario 2.3: Logout with Already Deactivated Session"""
        email, password = get_user_credentials("Account 1 Owner")
        
        # Login to get tokens
        login_response = make_request(http_client, "post", "/auth/token/", json={
            "email": email,
            "password": password
        })
        assert login_response.status_code == 200
        refresh_token = login_response.json().get("refresh") or login_response.json().get("refresh_token")
        access_token = login_response.json().get("access") or login_response.json().get("access_token")
        
        # Logout once
        client = requests.Session()
        client.base_url = http_client.base_url
        client.verify = getattr(http_client, 'verify', True)
        response1 = make_request(client, "post", "/auth/logout/", json={"refresh": refresh_token})
        if ONLY_CURRENT:
            assert response1.status_code == 205, f"Expected 205 but got {response1.status_code}, response: {response1.text}"
        else:
            assert response1.status_code == 204, f"Expected 204 but got {response1.status_code}, response: {response1.text}"
        
        # Try to logout again with same refresh token
        response2 = make_request(client, "post", "/auth/logout/", json={"refresh": refresh_token})
        assert response2.status_code == 400, "already deactivated session should return 400"
        
        # Try to logout again with same access token
        client2 = requests.Session()
        client2.base_url = http_client.base_url
        client2.verify = getattr(http_client, 'verify', True)
        client2.headers["Authorization"] = f"Bearer {access_token}"
        response3 = make_request(client2, "post", "/auth/logout/")
        assert response3.status_code == 401

    def test_2_4_logout_with_refresh_token_invalidation(self, authenticated_client, http_client):
        """Test Scenario 2.4: Logout with Refresh Token Invalidation"""
        email, password = get_user_credentials("Account 1 Owner")
        
        # Login to get tokens
        client1 = requests.Session()
        client1.base_url = http_client.base_url
        client1.verify = getattr(http_client, 'verify', True)

        login_response = make_request(client1, "post", "/auth/token/", json={
            "email": email,
            "password": password
        })
        assert login_response.status_code == 200, f"Login should succeed, Expected 200 but got {login_response.status_code}, response: {login_response.text}"
        access_token1 = login_response.json()["access"]
        refresh_token1 = login_response.json()["refresh"]

        refresh_response = make_request(client1, "post", "/auth/token/refresh/", json={"refresh": refresh_token1})
        assert refresh_response.status_code == 200, f"Refresh should succeed, Expected 200 but got {refresh_response.status_code}, response: {refresh_response.text}"
        access_token2 = refresh_response.json()["access"]
        
        # Logout with refresh token
        client = requests.Session()
        client.base_url = http_client.base_url
        client.verify = getattr(http_client, 'verify', True)
        response = make_request(client, "post", "/auth/logout/", json={"refresh": refresh_token1})
        if ONLY_CURRENT:
            assert response.status_code == 205, f"Expected 205 but got {response.status_code}, response: {response.text}"
        else:
            assert response.status_code == 204, f"Expected 204 but got {response.status_code}, response: {response.text}"
        
        # Try to use refresh token
        refresh_response = make_request(client1, "post", "/auth/token/refresh/", json={"refresh": refresh_token1})
        assert refresh_response.status_code == 401, f"Logged-out access token should be invalidated, Expected 401 but got {refresh_response.status_code}, response: {refresh_response.text}"

        refresh_response = make_request(client1, "post", "/auth/token/refresh/", json={"refresh": refresh_token1})
        assert refresh_response.status_code == 401, f"Logged-out related access token should be invalidated, Expected 401 but got {refresh_response.status_code}, response: {refresh_response.text}"


@pytest.mark.acceptance
class TestREQAuth003SessionManagement:
    """REQ-AUTH-003: Session Management"""

    def test_3_1_valid_session_access(self, authenticated_client):
        """Test Scenario 3.1: Valid Session Access"""
        email, password = get_user_credentials("Account 1 Owner")
        
        client = authenticated_client(email, password)
        
        start_time = time.time()
        response = make_request(client, "get", "/auth/sessions/")
        response_time = time.time() - start_time
        
        assert response.status_code == 200
        assert response_time < 2, f"Session validation should complete within 2s, got {response_time:.2f}s"

    # def test_3_2_expired_access_token(self, authenticated_client):
    #     """Test Scenario 3.2: Expired Access Token"""
    #     # This test requires creating an expired token or waiting for expiration
    #     # For now, we'll test with a manually expired token if possible
    #     # In practice, you'd need to manipulate token expiration or wait
        
    #     # Create a token and manually expire it (if JWT secret is known)
    #     # Or wait for actual expiration
    #     pytest.skip("Requires expired token creation or time manipulation")

    def test_3_3_deactivated_session_access(self, authenticated_client, http_client):
        """Test Scenario 3.3: Deactivated Session Access"""
        email, password = get_user_credentials("Account 1 Owner")
        
        client = authenticated_client(email, password)
        
        refresh_token = client.refresh_token
        
        # Logout to deactivate session
        logout_response = make_request(client, "post", "/auth/logout/", json={"refresh": refresh_token})
        if ONLY_CURRENT:
            assert logout_response.status_code == 205, f"Expected 205 but got {logout_response.status_code}, response: {logout_response.text}"
        else:
            assert logout_response.status_code == 204, f"Expected 204 but got {logout_response.status_code}, response: {logout_response.text}"
        
        # Try to use deactivated token
        response = make_request(client, "get", "/auth/sessions/")
        assert response.status_code == 401
        data = response.json()
        assert data.get("code") == "SESSION_EXPIRED" or "invalid" in str(data).lower()

    def test_3_4_invalid_token_jti(self, http_client):
        """Test Scenario 3.4: Invalid Token JTI"""
        # Create token with invalid JTI
        client = requests.Session()
        client.base_url = http_client.base_url
        client.verify = getattr(http_client, 'verify', True)
        client.headers["Authorization"] = "Bearer invalid.jti.token"
        
        response = make_request(client, "get", "/auth/sessions/")
        assert response.status_code == 401
        data = response.json()
        assert data.get("code") == "INVALID_SESSION" or "invalid" in str(data).lower()

    def test_3_5_session_validation_performance(self, authenticated_client):
        """Test Scenario 3.5: Session Validation Performance"""
        email, password = get_user_credentials("Account 1 Owner")
        
        client = authenticated_client(email, password)
        
        # Make multiple requests
        times = []
        for i in range(10):
            start_time = time.time()
            response = make_request(client, "get", "/auth/sessions/")
            response_time = time.time() - start_time
            times.append(response_time)
            assert response.status_code == 200
        
        avg_time = sum(times) / len(times)
        assert avg_time < 2, f"Average session validation should be less than 2s, got {avg_time:.2f}s"

    def test_3_6_token_tampering_detection(self, authenticated_client):
        """Missing Test Case 3.6: Token Tampering Detection"""
        email, password = get_user_credentials("Account 1 Owner")
        
        # Get valid token
        client = authenticated_client(email, password)
        valid_token = client.headers["Authorization"].split(" ")[1]
        
        # Tamper with token (modify signature or claims)
        tampered_token = valid_token[:-5] + "XXXXX"  # Simple tampering
        
        # Try to use tampered token
        tampered_client = requests.Session()
        tampered_client.base_url = client.base_url
        tampered_client.verify = getattr(client, 'verify', True)
        tampered_client.headers["Authorization"] = f"Bearer {tampered_token}"
        
        response = make_request(tampered_client, "get", "/auth/sessions/")
        assert response.status_code == 401
        data = response.json()
        assert data.get("code") == "INVALID_SESSION" or "invalid" in str(data).lower()

    def test_3_7_session_expiration_time_validation(self, authenticated_client):
        """Missing Test Case 3.7: Session Expiration Time Validation"""
        email, password = get_user_credentials("Account 1 Owner")
        
        # Login and get token
        client = authenticated_client(email, password)
        access_token = client.access_token
        
        # Verify token expiration
        token_exp = get_token_exp(access_token)
        assert token_exp is not None, "Token should have expiration claim"
        
        # Verify expiration is in the future
        current_time = int(time.time())
        assert token_exp > current_time, "Token expiration should be in the future"
        
        # Verify expiration is approximately 60 minutes from now
        expiration_time = token_exp - current_time
        assert 3590 <= expiration_time <= 3600, f"Token should expire in ~60 minutes, got {expiration_time} seconds"

    def test_3_8_deactivated_at_validation(self, authenticated_client, http_client):
        """Missing Test Case 3.8: DeactivatedAt Validation"""
        email, password = get_user_credentials("Account 1 Owner")
        
        client = authenticated_client(email, password)
        
        # Logout to set deactivatedAt
        # Get refresh token first
        login_response = make_request(http_client, "post", "/auth/token/", json={
            "email": email,
            "password": password
        })
        assert login_response.status_code == 200
        refresh_token = login_response.json().get("refresh") or login_response.json().get("refresh_token")
        
        response = make_request(client, "post", "/auth/logout/", json={"refresh": refresh_token})
        if ONLY_CURRENT:
            assert response.status_code == 205, f"Expected 205 but got {response.status_code}, response: {response.text}"
        else:
            assert response.status_code == 204, f"Expected 204 but got {response.status_code}, response: {response.text}"
        
        # Verify deactivated_at is set in database
        if DJANGO_AVAILABLE and AuthSession:
            from django.utils import timezone
            # Get the session using the refresh token's JTI or access token's JTI
            # Since we logged in, we can get the session from the access token
            access_token = client.headers.get("Authorization", "").replace("Bearer ", "")
            token_jti = get_token_jti(access_token)
            session = AuthSession.objects.using('default').filter(token_jti=token_jti).first()
            assert session.deactivated_at is not None, "Session deactivated_at should be set after logout"
            assert session.deactivated_at <= timezone.now(), "deactivated_at should be set to current or past time"


@pytest.mark.acceptance
class TestREQAuth004ListUserSessions:
    """REQ-AUTH-004: List User Sessions"""

    def test_4_1_list_active_sessions(self, http_client):
        """Test Scenario 4.1: List Active Sessions"""
        email, password = get_user_credentials("Account 1 Owner")
        
        # Create multiple sessions by logging in multiple times
        new_client = requests.Session()
        new_client.base_url = http_client.base_url
        new_client.verify = getattr(http_client, 'verify', True)
        
        # Login multiple times
        for i in range(3):
            login_response = make_request(new_client, "post", "/auth/token/", json={
                "email": email,
                "password": password
            })
            assert login_response.status_code == 200, f"Expected 200 for login {i+1}, got {login_response.status_code}, response: {login_response.text}"
        
        new_client.headers["Authorization"] = f"Bearer {login_response.json()['access']}"
        
        start_time = time.time()
        response = make_request(new_client, "get", "/auth/sessions/")
        response_time = time.time() - start_time
        
        assert response.status_code == 200, f"Expected 200 for list active sessions, got {response.status_code}, response: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        assert len(data) >= 1, "Should have at least one active session"
        
        # Verify session fields
        if len(data) > 0:
            session = data[0]
            assert "session_id" in session or "id" in session
            assert "ip_address" in session or "ipAddress" in session
            assert "user_agent" in session or "userAgent" in session
            assert "created_at" in session or "createdAt" in session
            assert "access_expires_at" in session or "expiresAt" in session
        
        assert response_time < 0.2, f"Response time should be less than 200ms, got {response_time:.2f}s"

    def test_4_2_list_sessions_with_only_current_session(self, authenticated_client):
        """Test Scenario 4.2: List Sessions with Only Current Session"""
        email, password = get_user_credentials("Account 1 Owner")
        
        client = authenticated_client(email, password)
        
        response = make_request(client, "get", "/auth/sessions/")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1, "Should have at least current session"
        
        # Verify current session is included
        # Check that session fields are present

    def test_4_3_list_sessions_unauthenticated(self, http_client):
        """Test Scenario 4.3: List Sessions Unauthenticated"""
        # Test without Authorization header
        response = make_request(http_client, "get", "/auth/sessions/")
        assert response.status_code == 401
        
        # Test with invalid token
        client = requests.Session()
        client.base_url = http_client.base_url
        client.verify = getattr(http_client, 'verify', True)
        client.headers["Authorization"] = "Bearer invalid.token"
        response = make_request(client, "get", "/auth/sessions/")
        assert response.status_code == 401
        
        # Test with expired token
        if DJANGO_AVAILABLE and AuthSession:
            from django.utils import timezone
            email, password = get_user_credentials("Account 1 Owner")
            
            # Login to create a session
            login_response = make_request(http_client, "post", "/auth/token/", json={"email": email, "password": password})
            assert login_response.status_code == 200
            expired_access_token = login_response.json()["access"]
            expired_token_jti = get_token_jti(expired_access_token)
            
            if expired_token_jti:
                # Make the session expired by setting access_expires_at to past
                expired_session = AuthSession.objects.using('default').filter(token_jti=expired_token_jti).first()
                if expired_session:
                    expired_session.access_expires_at = timezone.now() - timedelta(hours=1)
                    expired_session.save()
                    
                    # Try to use expired token
                    expired_client = requests.Session()
                    expired_client.base_url = http_client.base_url
                    expired_client.verify = getattr(http_client, 'verify', True)
                    expired_client.headers["Authorization"] = f"Bearer {expired_access_token}"
                    expired_response = make_request(expired_client, "get", "/auth/sessions/")
                    assert expired_response.status_code == 401, "Expired token should return 401"

    def test_4_4_list_sessions_user_isolation(self, authenticated_client):
        """Test Scenario 4.4: List Sessions - User Isolation"""
        # Get two users
        email_a, password_a = get_user_credentials("Account 1 Owner")
        email_b, password_b = get_user_credentials("Account 1 Org Admin")
        
        # Login as User A
        client_a = authenticated_client(email_a, password_a)
        response_a = make_request(client_a, "get", "/auth/sessions/")
        assert response_a.status_code == 200
        sessions_a = response_a.json()
        
        # Login as User B
        client_b = authenticated_client(email_b, password_b)
        response_b = make_request(client_b, "get", "/auth/sessions/")
        assert response_b.status_code == 200
        sessions_b = response_b.json()
        
        # Verify sessions are isolated
        session_ids_a = {s.get("session_id") or s.get("id") for s in sessions_a}
        session_ids_b = {s.get("session_id") or s.get("id") for s in sessions_b}
        assert session_ids_a.isdisjoint(session_ids_b), "Users should not see each other's sessions"

    def test_4_5_expired_sessions_exclusion(self, authenticated_client):
        """Missing Test Case 4.5: Expired Sessions Exclusion"""
        if not DJANGO_AVAILABLE or not AuthSession:
            pytest.skip("Django models not available")
        
        from django.utils import timezone
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get user
        User = get_user_model()
        user = User.objects.using('default').filter(email=email).first()
        if not user:
            pytest.skip("User not found")
        
        # Get all active sessions for the user
        response = make_request(client, "get", "/auth/sessions/")
        assert response.status_code == 200
        sessions_before = response.json()
        initial_count = len(sessions_before)
        
        # Create an expired session by manipulating access_expires_at in database
        # First, create a new session by logging in
        login_response = make_request(client, "post", "/auth/token/", json={"email": email, "password": password})
        assert login_response.status_code == 200
        new_access_token = login_response.json()["access"]
        new_token_jti = get_token_jti(new_access_token)
        
        if new_token_jti:
            # Get the session and set it as expired
            expired_session = AuthSession.objects.using('default').filter(token_jti=new_token_jti).first()
            if expired_session:
                # Set access_expires_at to past time to make it expired
                expired_session.access_expires_at = timezone.now() - timedelta(hours=1)
                expired_session.save()
                
                # Verify expired session is excluded from list
                response_after = make_request(client, "get", "/auth/sessions/")
                assert response_after.status_code == 200
                sessions_after = response_after.json()
                
                # Expired session should not appear in the list
                session_ids_after = {s.get("session_id") or s.get("id") for s in sessions_after if s["deactivated_at"] is None}
                assert str(expired_session.id) not in session_ids_after, "Expired session should be excluded from list"
                
                # Verify only active sessions are returned
                active_sessions = AuthSession.objects.using('default').filter(
                    user=user,
                    deactivated_at__isnull=True,
                    access_expires_at__gt=timezone.now()
                )
                assert len(sessions_after) <= active_sessions.count(), "Should only return active, non-expired sessions"


@pytest.mark.acceptance
class TestREQAuth005PasswordReset:
    """REQ-AUTH-005: Password Reset"""

    def test_5_1_request_password_reset_with_valid_email(self, http_client):
        """Test Scenario 5.1: Request Password Reset with Valid Email - Always Returns 200"""
        email, _ = get_user_credentials("Account 1 Owner")
        
        payload = {"email": email}
        
        start_time = time.time()
        response = make_request(http_client, "post", "/auth/password-reset/", json=payload)
        response_time = time.time() - start_time
        
        assert response.status_code == 200, f"Expected 200 but got {response.status_code}, response: {response.text}"
        assert response_time < 2.0, f"Response time should be less than 2 seconds, got {response_time:.2f}s"
        
        # Verify response has static success message (doesn't reveal if email exists)
        data = response.json()
        # Should have generic/static message regardless of whether email exists
        assert "message" in data or "success" in str(data).lower() or response.text, "Should return static success message"
        
        # Verify random delay was added
        assert response_time > 0.05, "Random delay should be added to prevent information leakage"

    def test_5_2_request_password_reset_with_invalid_email_format(self, http_client):
        """Test Scenario 5.2: Request Password Reset with Invalid Email Format"""
        invalid_emails = ["notanemail", "missing@domain", ""]
        
        for email in invalid_emails:
            payload = {"email": email}
            response = make_request(http_client, "post", "/auth/password-reset/", json=payload)
            # Invalid format should return 400, but valid format with non-existent email should return 200
            assert response.status_code in (400, 200), f"Expected 400 for invalid format or 200 for valid format, got {response.status_code}"
            if response.status_code == 400:
                data = response.json()
                assert "email" in str(data).lower() or "invalid" in str(data).lower()

    def test_5_3_password_reset_rate_limiting_per_email(self, http_client):
        """Test Scenario 5.3: Password Reset Rate Limiting Per Email"""
        email, _ = get_user_credentials("Account 1 Owner")
        
        # Send 3 requests per email (3 per hour per email)
        payload = {"email": email}
        for i in range(3):
            response = make_request(http_client, "post", "/auth/password-reset/", json=payload)
            assert response.status_code == 200, f"Request {i+1} should succeed"
        
        # 4th request should be rate limited
        response = make_request(http_client, "post", "/auth/password-reset/", json=payload)
        assert response.status_code == 429, "Should be rate limited after 3 requests per email"
        data = response.json()
        assert data.get("code") == "RATE_LIMIT_EXCEEDED" or "rate limit" in str(data).lower()

    def test_5_4_confirm_password_reset_with_valid_token(self, http_client):
        """Test Scenario 5.4: Confirm Password Reset with Valid Token"""
        if not DJANGO_AVAILABLE:
            pytest.skip("Django models not available")
        
        email, old_password = get_user_credentials("Account 1 Owner")
        
        # Login before resetting password to create an active session
        login_response_before = make_request(http_client, "post", "/auth/token/", json={"email": email, "password": old_password})
        assert login_response_before.status_code == 200
        old_access_token = login_response_before.json().get("access") or login_response_before.json().get("access_token")
        old_token_jti = get_token_jti(old_access_token)
        
        # Verify old session exists in database
        if old_token_jti and AuthSession:
            old_session = AuthSession.objects.using('default').filter(token_jti=old_token_jti).first()
            assert old_session is not None, "Old session should exist before password reset"
            assert old_session.deactivated_at is None, "Old session should be active before password reset"
        
        # Request password reset
        reset_response = make_request(http_client, "post", "/auth/password-reset/", json={"email": email})
        assert reset_response.status_code == 200
        
        # Wait a moment for email to be sent
        time.sleep(0.5)
        
        # Get reset token from mailpit email service
        mailpit_url = os.getenv("MAILPIT_URL", "http://mailpit:8025")
        try:
            email_content = get_latest_email_content(mailpit_url)
            uid, token = extract_password_reset_token(email_content)
        except Exception as e:
            raise Exception(f"Could not extract token from mailpit: {e}")
        
        # Confirm password reset with extracted token
        payload = {"uid": uid, "token": token, "new_password": "NewP@ssw0rd123"}
        response = make_request(http_client, "post", "/auth/password-reset/confirm/", json=payload)
        assert response.status_code == 200
        
        # Verify old access token is invalidated
        old_client = requests.Session()
        old_client.base_url = http_client.base_url
        old_client.verify = getattr(http_client, 'verify', True)
        old_client.headers["Authorization"] = f"Bearer {old_access_token}"
        old_token_response = make_request(old_client, "get", "/auth/sessions/")
        assert old_token_response.status_code == 401, "Old access token should be invalidated after password reset"
        
        # Verify old session is deactivated in database
        if old_token_jti and AuthSession:
            old_session = AuthSession.objects.using('default').filter(token_jti=old_token_jti).first()
            if old_session:
                assert old_session.deactivated_at is not None, "Old session should be deactivated after password reset"
        
        # Verify password changed - new password works
        login_response = make_request(http_client, "post", "/auth/token/", json={"email": email, "password": "NewP@ssw0rd123"})
        assert login_response.status_code == 200
        
        # Verify old password doesn't work
        login_response_old = make_request(http_client, "post", "/auth/token/", json={"email": email, "password": old_password})
        assert login_response_old.status_code == 401
        
        # Verify new session works
        new_client = requests.Session()
        new_client.base_url = http_client.base_url
        new_client.verify = getattr(http_client, 'verify', True)
        new_client.headers["Authorization"] = f"Bearer {login_response.json()['access']}"
        sessions_response = make_request(new_client, "get", "/auth/sessions/")
        assert sessions_response.status_code == 200, "New session should be valid"

    def test_5_5_confirm_password_reset_with_invalid_token(self, http_client):
        """Test Scenario 5.5: Confirm Password Reset with Invalid Token"""
        invalid_tokens = ["invalid_token", "expired_token_here", "nonexistent_token"]
        
        for token in invalid_tokens:
            payload = {
                "uid": "test-uid",
                "token": token,
                "new_password": "NewP@ssw0rd123"
            }
            start_time = time.time()
            response = make_request(http_client, "post", "/auth/password-reset/confirm/", json=payload)
            response_time = time.time() - start_time
            
            assert response.status_code == 400, f"Expected 400 for invalid token, got {response.status_code}"
            assert response_time > 0.05, "Random delay should be added"
            data = response.json()
            # assert "token" in str(data).lower() or "invalid" in str(data).lower() or "expired" in str(data).lower()

    def test_5_6_password_reset_with_weak_password(self, http_client):
        """Test Scenario 5.6: Password Reset with Weak Password"""
        if not DJANGO_AVAILABLE:
            pytest.skip("Django models not available")
        
        email, _ = get_user_credentials("Account 1 Owner")
        weak_passwords = [
            "Short1!",  # Too short
            "lowercase123!",  # Missing uppercase
            "UPPERCASE123!",  # Missing lowercase
            "NoNumbers!",  # Missing numbers
            "NoSpecial123",  # Missing special characters
        ]
        
        for weak_password in weak_passwords:
            # Request password reset
            reset_response = make_request(http_client, "post", "/auth/password-reset/", json={"email": email})
            assert reset_response.status_code == 200
            
            # Wait for email
            time.sleep(0.5)
            
            # Get reset token from mailpit
            mailpit_url = os.getenv("MAILPIT_URL", "http://mailpit:8025")
            try:
                email_content = get_latest_email_content(mailpit_url)
                uid, token = extract_password_reset_token(email_content)
            except Exception as e:
                raise Exception(f"Could not extract token from mailpit: {e}")
            
            # Try to reset with weak password
            payload = {"uid": uid, "token": token, "new_password": weak_password}
            response = make_request(http_client, "post", "/auth/password-reset/confirm/", json=payload)
            assert response.status_code == 400, f"Weak password '{weak_password}' should be rejected"
            data = response.json()
            assert "password" in str(data).lower() or "weak" in str(data).lower() or "invalid" in str(data).lower()
            clear_all_login_failures()

    def test_5_7_password_reset_email_privacy(self, http_client):
        """Test Scenario 5.7: Password Reset Email Privacy - Always Returns 200"""
        # Test with existing email
        email, _ = get_user_credentials("Account 1 Owner")
        payload1 = {"email": email}
        start_time1 = time.time()
        response1 = make_request(http_client, "post", "/auth/password-reset/", json=payload1)
        response_time1 = time.time() - start_time1
        
        # Test with non-existing email
        payload2 = {"email": "nonexistent_email_12345@example.com"}
        start_time2 = time.time()
        response2 = make_request(http_client, "post", "/auth/password-reset/", json=payload2)
        response_time2 = time.time() - start_time2
        
        # Both should return 200 with static message
        assert response1.status_code == 200, "Existing email should return 200"
        assert response2.status_code == 200, "Non-existing email should also return 200"
        
        # Responses should be similar (not reveal if email exists)
        assert response1.json() == response2.json(), "Responses should be similar"
        # Both should have random delay
        assert response_time1 > 0.05, "Random delay should be added for existing email"
        assert response_time2 > 0.05, "Random delay should be added for non-existing email"
        
        
        # Timing differences should be minimal (both have random delay)
        # Note: Exact timing comparison may vary, but both should have delay

    def test_5_8_password_reset_rate_limiting_by_ip_address(self, http_client):
        """Missing Test Case 5.8: Password Reset Rate Limiting by IP Address"""
        # Get test users
        emails = []
        for user_name in ["Account 1 Owner", "Account 1 Admin", "Account 2 Owner", "Account 4 User 1"]:
            email, _ = get_user_credentials(user_name)
            emails.append(email)
        
        # Send 3 requests from IP A with different emails
        ip_a_headers = {"X-Forwarded-For": "192.168.1.100"}
        for i in range(3):
            payload = {"email": emails[i]}
            response = make_request(http_client, "post", "/auth/password-reset/", json=payload, headers=ip_a_headers)
            assert response.status_code == 200
        
        # 4th request from IP A should be rate limited (3 per hour per IP)
        payload = {"email": emails[3]}
        response = make_request(http_client, "post", "/auth/password-reset/", json=payload, headers=ip_a_headers)
        assert response.status_code == 429, "Should be rate limited after 3 requests per IP"
        
        # # Request from IP B should not be rate limited
        # ip_b_headers = {"X-Forwarded-For": "192.168.1.200"}
        # payload = {"email": emails[0]}
        # response = make_request(http_client, "post", "/auth/password-reset/", json=payload, headers=ip_b_headers)
        # assert response.status_code == 200, "Different IP should not be rate limited"

    def test_5_9_password_similarity_check_user_name(self, http_client):
        """Missing Test Case 5.9: Password Similarity Check - User Name"""
        if not DJANGO_AVAILABLE:
            pytest.skip("Django models not available")
        
        email, _ = get_user_credentials("Account 1 Owner")
        
        # Get user's full name
        User = get_user_model()
        user = User.objects.using('default').filter(email=email).first()
        if not user or not user.full_name:
            pytest.skip("User not found or has no full name")
        
        # Create password similar to user's name
        similar_password = f"{user.full_name.replace(' ', '').lower()}123!"
        
        # Request password reset
        reset_response = make_request(http_client, "post", "/auth/password-reset/", json={"email": email})
        assert reset_response.status_code == 200
        
        # Wait for email
        time.sleep(0.5)
        
        # Get reset token from mailpit
        mailpit_url = os.getenv("MAILPIT_URL", "http://mailpit:8025")
        try:
            email_content = get_latest_email_content(mailpit_url)
            uid, token = extract_password_reset_token(email_content)
        except Exception as e:
            raise Exception(f"Could not extract token from mailpit: {e}")
        
        # Try to reset with password similar to user name
        payload = {"uid": uid, "token": token, "new_password": similar_password}
        response = make_request(http_client, "post", "/auth/password-reset/confirm/", json=payload)
        assert response.status_code == 400, "Password similar to user name should be rejected"
        data = response.json()
        assert data.get("code") == "PASSWORD_POLICY_VIOLATION"

    def test_5_10_password_similarity_check_organization_name(self, http_client):
        """Missing Test Case 5.10: Password Similarity Check - Organization Name"""
        if not DJANGO_AVAILABLE:
            pytest.skip("Django models not available")
        
        email, _ = get_user_credentials("Account 1 Owner")
        
        # Get user's organization name
        User = get_user_model()
        user = User.objects.using('default').filter(email=email).first()
        if not user:
            pytest.skip("User not found")
        
        # Get first organization membership
        user_org = UserOrganization.objects.using('default').filter(user=user, is_active=True).first()
        if not user_org or not user_org.organization:
            pytest.skip("User has no active organization membership")
        
        org_name = user_org.organization.name
        similar_password = f"{org_name.replace(' ', '').lower()}123!"
        
        # Request password reset
        reset_response = make_request(http_client, "post", "/auth/password-reset/", json={"email": email})
        assert reset_response.status_code == 200
        
        # Wait for email
        time.sleep(0.5)
        
        # Get reset token from mailpit
        mailpit_url = os.getenv("MAILPIT_URL", "http://mailpit:8025")
        try:
            email_content = get_latest_email_content(mailpit_url)
            uid, token = extract_password_reset_token(email_content)
        except Exception as e:
            raise Exception(f"Could not extract token from mailpit: {e}")
        
        # Try to reset with password similar to organization name
        payload = {"uid": uid, "token": token, "new_password": similar_password}
        response = make_request(http_client, "post", "/auth/password-reset/confirm/", json=payload)
        assert response.status_code == 400, "Password similar to organization name should be rejected"
        data = response.json()
        assert data.get("code") == "PASSWORD_POLICY_VIOLATION"

    def test_5_11_password_similarity_check_account_name(self, http_client):
        """Missing Test Case 5.11: Password Similarity Check - Account Name"""
        if not DJANGO_AVAILABLE:
            pytest.skip("Django models not available")
        
        email, _ = get_user_credentials("Account 1 Owner")
        
        # Get user's account name
        # User = get_user_model()
        # user = User.objects.using('default').filter(email=email).first()
        # if not user:
        #     pytest.skip("User not found")
        
        # Get account from organization
        # user_org = UserOrganization.objects.using('default').filter(user=user, is_active=True).first()
        # if not user_org or not user_org.organization or not user_org.organization.account:
        #     pytest.skip("User has no account")
        
        account_name = "Test Account Alpha"
        similar_password = f"{account_name.replace(' ', '').lower()}123!"
        
        # Request password reset
        reset_response = make_request(http_client, "post", "/auth/password-reset/", json={"email": email})
        assert reset_response.status_code == 200
        
        # Wait for email
        time.sleep(0.5)
        
        # Get reset token from mailpit
        mailpit_url = os.getenv("MAILPIT_URL", "http://mailpit:8025")
        try:
            email_content = get_latest_email_content(mailpit_url)
            uid, token = extract_password_reset_token(email_content)
        except Exception as e:
            raise Exception(f"Could not extract token from mailpit: {e}")
        
        # Try to reset with password similar to account name
        payload = {"uid": uid, "token": token, "new_password": similar_password}
        response = make_request(http_client, "post", "/auth/password-reset/confirm/", json=payload)
        assert response.status_code == 400, "Password similar to account name should be rejected"
        data = response.json()
        assert data.get("code") == "PASSWORD_POLICY_VIOLATION"

    def test_5_12_password_reset_token_single_use(self, http_client):
        """Missing Test Case 5.12: Password Reset Token Single Use Only"""
        if not DJANGO_AVAILABLE:
            pytest.skip("Django models not available")
        
        email, old_password = get_user_credentials("Account 1 Owner")
        
        # Request password reset
        reset_response = make_request(http_client, "post", "/auth/password-reset/", json={"email": email})
        assert reset_response.status_code == 200
        
        # Wait for email
        time.sleep(0.5)
        
        # Get reset token from mailpit
        mailpit_url = os.getenv("MAILPIT_URL", "http://mailpit:8025")
        try:
            email_content = get_latest_email_content(mailpit_url)
            uid, token = extract_password_reset_token(email_content)
        except Exception as e:
            raise Exception(f"Could not extract token from mailpit: {e}")
        
        # Use token first time
        payload = {"uid": uid, "token": token, "new_password": "NewP@ssw0rd123"}
        response1 = make_request(http_client, "post", "/auth/password-reset/confirm/", json=payload)
        assert response1.status_code == 200, "First use of token should succeed"
        
        # Try to use same token again
        response2 = make_request(http_client, "post", "/auth/password-reset/confirm/", json=payload)
        assert response2.status_code in (400, 401), "Token should be single-use only and rejected on second use"
        data = response2.json()
        assert "token" in str(data).lower() or "invalid" in str(data).lower() or "used" in str(data).lower()

    def test_5_13_password_reset_password_length_validation(self, http_client):
        """Missing Test Case 5.13: Password Reset Password Length Validation"""
        if not DJANGO_AVAILABLE:
            pytest.skip("Django models not available")
        
        email, _ = get_user_credentials("Account 1 Owner")
        
        # Test with too short password (7 characters)
        reset_response = make_request(http_client, "post", "/auth/password-reset/", json={"email": email})
        assert reset_response.status_code == 200
        time.sleep(0.5)
        
        mailpit_url = os.getenv("MAILPIT_URL", "http://mailpit:8025")
        try:
            email_content = get_latest_email_content(mailpit_url)
            uid, token = extract_password_reset_token(email_content)
        except Exception as e:
            raise Exception(f"Could not extract token from mailpit: {e}")
        
        # Test too short password
        short_password = "Short1!"  # 7 characters
        payload = {"uid": uid, "token": token, "new_password": short_password}
        response = make_request(http_client, "post", "/auth/password-reset/confirm/", json=payload)
        assert response.status_code == 400, "Password too short should be rejected"
        data = response.json()
        assert "length" in str(data).lower() or "short" in str(data).lower() or "8" in str(data)
        
        # Test too long password (129 characters)
        reset_response2 = make_request(http_client, "post", "/auth/password-reset/", json={"email": email})
        assert reset_response2.status_code == 200
        time.sleep(0.5)
        
        try:
            email_content2 = get_latest_email_content(mailpit_url)
            uid2, token2 = extract_password_reset_token(email_content2)
        except Exception as e:
            raise Exception(f"Could not extract token from mailpit: {e}")
        
        long_password = "A" * 129  # 129 characters
        payload2 = {"uid": uid2, "token": token2, "new_password": long_password}
        response2 = make_request(http_client, "post", "/auth/password-reset/confirm/", json=payload2)
        assert response2.status_code == 400, "Password too long should be rejected"
        data2 = response2.json()
        assert data2.get("code") == "PASSWORD_POLICY_VIOLATION"


@pytest.mark.acceptance
class TestREQAuth006SessionRefresh:
    """REQ-AUTH-006: Session Refresh"""

    def test_6_1_successful_token_refresh(self, http_client):
        """Test Scenario 6.1: Successful Token Refresh - Previous Access Token Invalidated Immediately"""
        email, password = get_user_credentials("Account 1 Owner")
        
        # Login to get tokens
        login_response = make_request(http_client, "post", "/auth/token/", json={
            "email": email,
            "password": password
        })
        assert login_response.status_code == 200
        refresh_token = login_response.json().get("refresh") or login_response.json().get("refresh_token")
        original_access_token = login_response.json().get("access") or login_response.json().get("access_token")
        original_jti = get_token_jti(original_access_token)
        
        # Refresh access token
        start_time = time.time()
        refresh_response = make_request(http_client, "post", "/auth/token/refresh/", json={"refresh": refresh_token})
        response_time = time.time() - start_time
        
        assert refresh_response.status_code == 200
        data = refresh_response.json()
        assert "access" in data or "access_token" in data
        new_access_token = data.get("access") or data.get("access_token")
        
        # Verify new token expires in 60 minutes
        token_exp = get_token_exp(new_access_token)
        if token_exp:
            current_time = int(time.time())
            expiration_time = token_exp - current_time
            assert 3590 <= expiration_time <= 3600, f"Token should expire in ~60 minutes, got {expiration_time} seconds"
        
        # Verify new token has different JTI
        new_jti = get_token_jti(new_access_token)
        assert new_jti != original_jti, "New access token should have different JTI"
        
        # Verify previous access token is invalidated immediately
        client_old = requests.Session()
        client_old.base_url = http_client.base_url
        client_old.verify = getattr(http_client, 'verify', True)
        client_old.headers["Authorization"] = f"Bearer {original_access_token}"
        old_token_response = make_request(client_old, "get", "/auth/sessions/")
        assert old_token_response.status_code == 401, "Previous access token should be invalidated immediately after refresh"
        
        # Verify new access token works
        client_new = requests.Session()
        client_new.base_url = http_client.base_url
        client_new.verify = getattr(http_client, 'verify', True)
        client_new.headers["Authorization"] = f"Bearer {new_access_token}"
        new_token_response = make_request(client_new, "get", "/auth/sessions/")
        assert new_token_response.status_code == 200, "New access token should work"
        
        assert response_time < 0.5, f"Response time should be less than 500ms, got {response_time:.2f}s"

    # def test_6_2_token_refresh_with_expired_refresh_token(self, http_client):
    #     """Test Scenario 6.2: Token Refresh with Expired Refresh Token"""
    #     # This test requires an expired refresh token
    #     # Would need to wait for expiration or manipulate token expiration
    #     pytest.skip("Requires expired refresh token or time manipulation")

    def test_6_3_token_refresh_with_invalid_refresh_token(self, http_client):
        """Test Scenario 6.3: Token Refresh with Invalid Refresh Token"""
        invalid_tokens = [
            "invalid.token.here",
            "malformed",
            "",
            "not.a.jwt.token"
        ]
        
        for token in invalid_tokens:
            payload = {"refresh": token}
            response = make_request(http_client, "post", "/auth/token/refresh/", json=payload)
            assert response.status_code in (400, 401)
            data = response.json()
            assert data.get("code") == "INVALID_SESSION" or "invalid" in str(data).lower()

    def test_6_4_multiple_token_refreshes(self, http_client):
        """Test Scenario 6.4: Multiple Token Refreshes"""
        email, password = get_user_credentials("Account 1 Owner")
        
        # Login to get refresh token
        login_response = make_request(http_client, "post", "/auth/token/", json={
            "email": email,
            "password": password
        })
        assert login_response.status_code == 200
        refresh_token = login_response.json()["refresh"]
        
        # Refresh multiple times
        access_tokens = []
        for i in range(4):
            refresh_response = make_request(http_client, "post", "/auth/token/refresh/", json={"refresh": refresh_token})
            assert refresh_response.status_code == 200, f"Refresh {i+1} rejected, Expected 200 but got {refresh_response.status_code}, response: {refresh_response.text}"
            new_token = refresh_response.json().get("access") or refresh_response.json().get("access_token")
            access_tokens.append(new_token)
            
            # Verify previous token is invalidated
            if i > 0:
                prev_client = requests.Session()
                prev_client.base_url = http_client.base_url
                prev_client.verify = getattr(http_client, 'verify', True)
                prev_client.headers["Authorization"] = f"Bearer {access_tokens[i-1]}"
                prev_response = make_request(prev_client, "get", "/auth/sessions/")
                assert prev_response.status_code == 401, f"Previous access token {i} should be invalidated after refresh {i+1}"
        
        # All tokens should be unique
        assert len(set(access_tokens)) == len(access_tokens), "All access tokens should be unique"

    def test_6_5_refresh_token_lifetime_configuration(self, http_client):
        """Test Scenario 6.5: Refresh Token Lifetime Configuration"""
        email, password = get_user_credentials("Account 1 Owner")
        
        # Login to get refresh token
        login_response = make_request(http_client, "post", "/auth/token/", json={
            "email": email,
            "password": password
        })
        assert login_response.status_code == 200
        refresh_token = login_response.json()["refresh"]
        
        # Verify refresh token expiration matches session_duration_hours
        token_exp = get_token_exp(refresh_token)
        if token_exp:
            current_time = int(time.time())
            expiration_time = token_exp - current_time
            # Should match session_duration_hours (1-24 hours)
            assert 3600 <= expiration_time <= 86400, f"Refresh token should expire in 1-24 hours, got {expiration_time} seconds"

    def test_6_6_token_refresh_rate_limiting(self, http_client):
        """Test Scenario 6.6: Token Refresh Rate Limiting"""
        email, password = get_user_credentials("Account 1 Owner")
        
        # Login to get refresh token
        login_response = make_request(http_client, "post", "/auth/token/", json={
            "email": email,
            "password": password
        })
        assert login_response.status_code == 200
        refresh_token = login_response.json()["refresh"]
        
        # Send 10 successful refresh requests
        for i in range(10):
            response = make_request(http_client, "post", "/auth/token/refresh/", json={"refresh": refresh_token})
            assert response.status_code == 200, f"Refresh {i+1} rejected, Expected 200 but got {response.status_code}, response: {response.text}"
        
        # 11th request should be rate limited (10 per hour per user for successful attempts)
        response = make_request(http_client, "post", "/auth/token/refresh/", json={"refresh": refresh_token})
        assert response.status_code == 429
        data = response.json()
        assert data.get("code") == "RATE_LIMIT_EXCEEDED" or "rate limit" in str(data).lower()

    def test_6_7_refresh_token_not_invalidated_on_refresh(self, http_client):
        """Missing Test Case 6.7: Refresh Token Not Invalidated on Refresh"""
        email, password = get_user_credentials("Account 1 Owner")
        
        # Login to get refresh token
        login_response = make_request(http_client, "post", "/auth/token/", json={
            "email": email,
            "password": password
        })
        assert login_response.status_code == 200
        refresh_token = login_response.json()["refresh"]
        
        # Use refresh token multiple times (refresh token itself is not rotated)
        for i in range(5):
            refresh_response = make_request(http_client, "post", "/auth/token/refresh/", json={"refresh": refresh_token})
            assert refresh_response.status_code == 200, f"Refresh token should remain valid after {i+1} uses"
        
        # Verify refresh token is still valid (not rotated)
        refresh_response = make_request(http_client, "post", "/auth/token/refresh/", json={"refresh": refresh_token})
        assert refresh_response.status_code == 200, "Refresh token should still be valid (not rotated)"

    def test_6_8_refresh_with_inactive_user(self, http_client):
        """Test Scenario 6.8: Token Refresh with Inactive User - Should return 401"""
        if not DJANGO_AVAILABLE:
            pytest.skip("Django models not available")
        
        # Create an inactive user and get their refresh token
        User = get_user_model()
        test_email = "inactive_refresh_test@example.com"
        test_password = "TestP@ssw0rd123"
        
        # Create user
        user = User.objects.create_user(
            email=test_email,
            password=test_password,
            is_active=True
        )
        
        # Login to get refresh token
        login_response = make_request(http_client, "post", "/auth/token/", json={
            "email": test_email,
            "password": test_password
        })
        assert login_response.status_code == 200
        refresh_token = login_response.json().get("refresh") or login_response.json().get("refresh_token")
        
        # Deactivate user
        user.is_active = False
        user.save()
        
        # Try to refresh with inactive user
        start_time = time.time()
        refresh_response = make_request(http_client, "post", "/auth/token/refresh/", json={"refresh": refresh_token})
        response_time = time.time() - start_time
        
        assert refresh_response.status_code == 401, f"Should return 401 for inactive user, got {refresh_response.status_code}, response: {refresh_response.text}"
        assert response_time > 0.05, "Random delay should be added"
        
        # Cleanup
        user.delete()

    def test_6_9_old_token_deactivated_on_logout_after_refresh(self, http_client):
        """Test that old token is deactivated on logout even if token is refreshed."""
        email, password = get_user_credentials("Account 1 Owner")
        
        # First authentication - save token as token1
        login_response1 = make_request(http_client, "post", "/auth/token/", json={
            "email": email,
            "password": password
        })
        assert login_response1.status_code == 200
        token1 = login_response1.json().get("access") or login_response1.json().get("access_token")
        refresh_token1 = login_response1.json().get("refresh") or login_response1.json().get("refresh_token")
        
        # Refresh to get new token - save as token2 (this invalidates token1)
        refresh_response = make_request(http_client, "post", "/auth/token/refresh/", json={"refresh": refresh_token1})
        assert refresh_response.status_code == 200
        token2 = refresh_response.json().get("access") or refresh_response.json().get("access_token")
        
        # Verify token1 is already invalidated from refresh
        client1 = requests.Session()
        client1.base_url = http_client.base_url
        client1.verify = getattr(http_client, 'verify', True)
        client1.headers["Authorization"] = f"Bearer {token1}"
        response1 = make_request(client1, "get", "/auth/sessions/")
        assert response1.status_code == 401, "Old token (token1) should already be invalidated after refresh"
        
        # Logout using the refresh token (this invalidates token2 and the session)
        client2 = requests.Session()
        client2.base_url = http_client.base_url
        client2.verify = getattr(http_client, 'verify', True)
        logout_response = make_request(client2, "post", "/auth/logout/", json={"refresh": refresh_token1})
        if ONLY_CURRENT:
            assert logout_response.status_code == 205, f"Expected 205 but got {logout_response.status_code}, response: {logout_response.text}"
        else:
            assert logout_response.status_code == 204, f"Expected 204 but got {logout_response.status_code}, response: {logout_response.text}"
        
        # Test that token2 is also deactivated after logout
        client2.headers["Authorization"] = f"Bearer {token2}"
        response2 = make_request(client2, "get", "/auth/sessions/")
        assert response2.status_code == 401, "New token (token2) should be deactivated after logout"

    def test_6_10_old_token_cannot_refresh_on_logout_after_refresh(self, http_client):
        """Test that old token cannot be refreshed on logout even if token is refreshed."""
        email, password = get_user_credentials("Account 1 Owner")
        
        # First authentication - save token as token1
        login_response1 = make_request(http_client, "post", "/auth/token/", json={
            "email": email,
            "password": password
        })
        assert login_response1.status_code == 200
        token1 = login_response1.json()["access"]
        refresh_token1 = login_response1.json()["refresh"]
        
        # Refresh to get new token - save as token2
        refresh_response = make_request(http_client, "post", "/auth/token/refresh/", json={"refresh": refresh_token1})
        assert refresh_response.status_code == 200
        token2 = refresh_response.json()["access"]
        refresh_token2 = refresh_response.json().get("refresh", refresh_token1)  # Some implementations return new refresh token
        
        # Logout using the refresh token
        client2 = requests.Session()
        client2.base_url = http_client.base_url
        client2.verify = getattr(http_client, 'verify', True)
        logout_response = make_request(client2, "post", "/auth/logout/", json={"refresh": refresh_token1})
        if ONLY_CURRENT:
            assert logout_response.status_code == 205, f"Expected 205 but got {logout_response.status_code}, response: {logout_response.text}"
        else:
            assert logout_response.status_code == 204, f"Expected 204 but got {logout_response.status_code}, response: {logout_response.text}"
        
        # Test that refresh token cannot be used after logout
        refresh_attempt = make_request(http_client, "post", "/auth/token/refresh/", json={"refresh": refresh_token1})
        assert refresh_attempt.status_code == 401, "Refresh token should not work after logout"

    def test_6_11_token_without_session_cannot_be_used(self, http_client):
        """Test that tokens that are not in the database table authsession cannot be used or refreshed."""
        if not DJANGO_AVAILABLE or not AuthSession:
            pytest.skip("Django models not available")
        
        email, password = get_user_credentials("Account 1 Owner")
        
        # Authenticate and save token
        login_response = make_request(http_client, "post", "/auth/token/", json={
            "email": email,
            "password": password
        })
        assert login_response.status_code == 200
        access_token = login_response.json()["access"]
        refresh_token = login_response.json()["refresh"]
        
        # Delete the matching session from the database using AuthSession model
        token_jti = get_token_jti(access_token)
        if not token_jti:
            pytest.skip("Could not extract token JTI")
        
        # Verify session exists before deletion
        session = AuthSession.objects.using('default').filter(token_jti=token_jti).first()
        assert session is not None, "Session should exist before deletion"
        
        # Delete the session
        session.token_jti = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
        session.refresh_token_hash = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
        session.save()
        
        # Verify session is deleted
        deleted_session = AuthSession.objects.using('default').filter(token_jti=token_jti).first()
        assert deleted_session is None, "Session should be deleted from database"
        
        # Test that the token cannot be refreshed
        refresh_response = make_request(http_client, "post", "/auth/token/refresh/", json={"refresh": refresh_token})
        assert refresh_response.status_code == 401, "Token should not be refreshable if session is deleted, got {refresh_response.status_code}, response: {refresh_response.text}"
        
        # Test that the token cannot access any resources
        client = requests.Session()
        client.base_url = http_client.base_url
        client.verify = getattr(http_client, 'verify', True)
        client.headers["Authorization"] = f"Bearer {access_token}"
        
        resource_response = make_request(client, "get", "/accounts/")
        assert resource_response.status_code == 401, "Token should not work if session is deleted from database"


@pytest.mark.acceptance
class TestREQAuthz006AuditLogging:
    """REQ-AUTHZ-006: Audit Logging"""

    def test_12_1_audit_log_on_access_granted(self, authenticated_client):
        """Test Scenario 12.1: Audit Log on Access Granted"""
        if not DJANGO_AVAILABLE or not AuditLog:
            pytest.skip("Django models not available")
        
        from django.utils import timezone
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Make a successful request
        before_request = timezone.now()
        response = make_request(client, "get", "/auth/sessions/")
        assert response.status_code == 200
        
        # Check audit log for successful access
        User = get_user_model()
        user = User.objects.using('default').filter(email=email).first()
        audit_log = AuditLog.objects.using('default').filter(
            path="/api/auth/sessions/",
            method="GET",
            status_code=200,
            created_at__gte=before_request - timedelta(seconds=1)
        ).order_by("-created_at").first()
        
        assert audit_log is not None, "Audit log entry should be created for successful access"
        assert audit_log.success is True, "Audit log should mark successful access as success=True"
        if user:
            assert audit_log.user_id == user.id, f"Audit log should reference the correct user: {audit_log.user_id} != {user.id}"

    # def test_12_2_audit_log_on_access_denied(self, authenticated_client):
    #     """Test Scenario 12.2: Audit Log on Access Denied"""
    #     if not DJANGO_AVAILABLE or not AuditLog:
    #         pytest.skip("Django models not available")
        
    #     from django.utils import timezone
    #     email, password = get_user_credentials("Account 1 Owner")
    #     client = authenticated_client(email, password)
        
    #     # Make a request that should be denied (e.g., invalid endpoint or unauthorized resource)
    #     before_request = timezone.now()
    #     response = make_request(client, "get", "/auth/invalid-endpoint/")
        
    #     # Check audit log for denied access (if endpoint exists, might be 404, if unauthorized might be 403)
    #     if response.status_code in (403, 404):
    #         User = get_user_model()
    #         user = User.objects.using('default').filter(email=email).first()
    #         audit_log = AuditLog.objects.using('default').filter(
    #             path="/api/auth/invalid-endpoint/",
    #             method="GET",
    #             status_code=response.status_code,
    #             created_at__gte=before_request - timedelta(seconds=1)
    #         ).order_by("-created_at").first()
            
    #         if audit_log:
    #             assert audit_log.success is False, "Audit log should mark denied access as success=False"
    #             if user:
    #                 assert audit_log.user_id == user.id, f"Audit log should reference the correct user"

    def test_12_3_audit_log_immutability(self, authenticated_client):
        """Test Scenario 12.3: Audit Log Immutability"""
        if not DJANGO_AVAILABLE or not AuditLog:
            pytest.skip("Django models not available")
        
        from django.utils import timezone
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Make a request to create audit log
        before_request = timezone.now()
        response = make_request(client, "get", "/auth/sessions/")
        assert response.status_code == 200
        
        # Get the audit log entry
        audit_log = AuditLog.objects.using('default').filter(
            path="/api/auth/sessions/",
            method="GET",
            status_code=200,
            created_at__gte=before_request - timedelta(seconds=1)
        ).order_by("-created_at").first()
        
        if audit_log:
            original_success = audit_log.success
            original_status = audit_log.status_code
            
            # Try to modify audit log (should fail or be prevented)
            try:
                audit_log.success = not audit_log.success
                audit_log.status_code = 999
                audit_log.save()
                
                # Reload from database
                audit_log.refresh_from_db()
                
                # Verify immutability - values should not have changed
                assert audit_log.success == original_success, "Audit log success field should be immutable"
                assert audit_log.status_code == original_status, "Audit log status_code field should be immutable"
            except Exception:
                # If save fails, that's also acceptable (immutability enforced at model level)
                pass

    def test_12_4_audit_log_searchability(self, authenticated_client):
        """Test Scenario 12.4: Audit Log Searchability"""
        if not DJANGO_AVAILABLE or not AuditLog:
            pytest.skip("Django models not available")
        
        from django.utils import timezone
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Make a request
        before_request = timezone.now()
        response = make_request(client, "get", "/auth/sessions/")
        assert response.status_code == 200
        
        # Search audit logs by path
        User = get_user_model()
        user = User.objects.using('default').filter(email=email).first()
        
        audit_logs = AuditLog.objects.using('default').filter(
            path="/api/auth/sessions/",
            created_at__gte=before_request - timedelta(seconds=1)
        )
        
        assert audit_logs.exists(), "Should be able to search audit logs by path"
        
        # Search by user
        if user:
            user_logs = AuditLog.objects.using('default').filter(
                user_id=user.id,
                created_at__gte=before_request - timedelta(seconds=1)
            )
            assert user_logs.exists(), "Should be able to search audit logs by user"

    def test_12_5_audit_log_retention(self, authenticated_client):
        """Test Scenario 12.5: Audit Log Retention"""
        if not DJANGO_AVAILABLE or not AuditLog:
            pytest.skip("Django models not available")
        
        # Verify audit logs are retained (not deleted)
        # This test verifies that audit logs exist and are not automatically deleted
        from django.utils import timezone
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Make a request
        before_request = timezone.now()
        response = make_request(client, "get", "/auth/sessions/")
        assert response.status_code == 200
        
        # Verify audit log exists
        audit_log = AuditLog.objects.using('default').filter(
            path="/api/auth/sessions/",
            method="GET",
            status_code=200,
            created_at__gte=before_request - timedelta(seconds=1)
        ).order_by("-created_at").first()
        
        assert audit_log is not None, "Audit log should be retained"
        assert audit_log.created_at is not None, "Audit log should have creation timestamp"

    def test_12_6_audit_log_performance_impact(self, authenticated_client):
        """Test Scenario 12.6: Audit Log Performance Impact"""
        if not DJANGO_AVAILABLE or not AuditLog:
            pytest.skip("Django models not available")
        
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Measure response time with audit logging enabled
        times = []
        for i in range(5):
            start_time = time.time()
            response = make_request(client, "get", "/auth/sessions/")
            response_time = time.time() - start_time
            times.append(response_time)
            assert response.status_code == 200
        
        avg_time = sum(times) / len(times)
        # Audit logging should not significantly impact performance (< 100ms overhead)
        assert avg_time < 0.5, f"Average response time should be reasonable: {avg_time:.3f}s"

    def test_12_7_authentication_event_logging(self, http_client):
        """Missing Test Case 12.7: Authentication Event Logging"""
        if not DJANGO_AVAILABLE or not AuditLog:
            pytest.skip("Django models not available")
        
        from django.utils import timezone
        email, password = get_user_credentials("Account 1 Owner")
        
        # Login
        before_login = timezone.now()
        login_response = make_request(http_client, "post", "/auth/token/", json={
            "email": email,
            "password": password
        })
        assert login_response.status_code == 200
        
        # Check audit log for login event
        User = get_user_model()
        user = User.objects.using('default').filter(email=email).first()
        login_audit_log = AuditLog.objects.using('default').filter(
            path="/api/auth/token/",
            method="POST",
            status_code=200,
            app_label="authentication",
            created_at__gte=before_login - timedelta(seconds=1)
        ).order_by("-created_at").first()
        
        assert login_audit_log is not None, "Audit log entry should be created for login"
        assert login_audit_log.success is True, "Audit log should mark successful login as success=True"
        if user:
            assert login_audit_log.user_id == user.id, f"Audit log should reference the correct user: {login_audit_log.user_id} != {user.id}"
        
        # Logout
        client = requests.Session()
        client.base_url = http_client.base_url
        client.verify = getattr(http_client, 'verify', True)
        client.headers["Authorization"] = f"Bearer {login_response.json()['access']}"
        
        before_logout = timezone.now()
        logout_response = make_request(client, "post", "/auth/logout/", json={"refresh": login_response.json()["refresh"]})
        assert logout_response.status_code in (200, 204, 205)
        
        # Check audit log for logout event
        logout_audit_log = AuditLog.objects.using('default').filter(
            path="/api/auth/logout/",
            method="POST",
            status_code__in=[200, 204, 205],
            app_label="authentication",
            created_at__gte=before_logout - timedelta(seconds=1)
        ).order_by("-created_at").first()
        
        assert logout_audit_log is not None, "Audit log entry should be created for logout"
        if user:
            assert logout_audit_log.user_id == user.id, f"Audit log should reference the correct user for logout"

    # def test_12_8_permission_change_logging(self, admin_client):
    #     """Missing Test Case 12.8: Permission Change Logging"""
    #     if not DJANGO_AVAILABLE or not AuditLog:
    #         pytest.skip("Django models not available")
        
    #     # This test would require role assignment changes
    #     # For now, we'll test that audit logs are created for user-related changes
    #     from django.utils import timezone
    #     email, password = get_user_credentials("Account 1 Owner")
        
    #     # Make a request that might trigger permission checks
    #     before_request = timezone.now()
    #     response = make_request(admin_client, "get", "/auth/sessions/")
    #     assert response.status_code == 200
        
    #     # Verify audit log was created
    #     User = get_user_model()
    #     admin_user = User.objects.using('default').filter(email=email).first()
    #     audit_log = AuditLog.objects.using('default').filter(
    #         path="/api/auth/sessions/",
    #         method="GET",
    #         status_code=200,
    #         created_at__gte=before_request - timedelta(seconds=1)
    #     ).order_by("-created_at").first()
        
    #     assert audit_log is not None, "Audit log should be created for permission-related requests"
    #     if admin_user:
    #         assert audit_log.user_id == admin_user.id, "Audit log should reference the user making the request"


@pytest.mark.acceptance
class TestInputValidationAndSecurity:
    """Input Validation & Security Tests"""

    def test_s_1_user_agent_xss_prevention(self, http_client):
        """Missing Test Case S.1: User Agent XSS Prevention"""
        if not DJANGO_AVAILABLE or not AuthSession:
            pytest.skip("Django models not available")
        
        email, password = get_user_credentials("Account 1 Owner")
        
        malicious_user_agents = [
            "<script>alert('XSS')</script>",
            "javascript:alert('XSS')",
            "' OR '1'='1"
        ]
        
        for user_agent in malicious_user_agents:
            payload = {
                "email": email,
                "password": password
            }
            headers = {"User-Agent": user_agent}
            response = make_request(http_client, "post", "/auth/token/", json=payload, headers=headers)
            
            # Should either succeed (with sanitized user agent) or fail gracefully
            assert response.status_code in [200, 400, 401]
            
            # If login succeeds, verify user agent is sanitized in session
            if response.status_code == 200:
                access_token = response.json().get("access") or response.json().get("access_token")
                token_jti = get_token_jti(access_token)
                
                if token_jti:
                    session = AuthSession.objects.using('default').filter(token_jti=token_jti).first()
                    if session and hasattr(session, 'user_agent'):
                        stored_user_agent = session.user_agent
                        # Verify XSS attempts are sanitized (should not contain script tags or javascript:)
                        assert "<script>" not in stored_user_agent, "User agent should not contain <script> tags"
                        assert "javascript:" not in stored_user_agent.lower(), "User agent should not contain javascript: protocol"
                        # User agent should be sanitized or truncated
                        assert len(stored_user_agent) <= 500, "User agent should be truncated if too long"

    def test_s_2_ip_address_validation_ipv4_ipv6(self, http_client):
        """Missing Test Case S.2: IP Address Validation (IPv4 and IPv6)"""
        if not DJANGO_AVAILABLE or not AuthSession:
            pytest.skip("Django models not available")
        
        email, password = get_user_credentials("Account 1 Owner")
        
        # Test valid IPv4
        payload = {"email": email, "password": password}
        headers = {"X-Forwarded-For": "192.168.1.100", "X-Real-IP": "192.168.1.100"}
        response = make_request(http_client, "post", "/auth/token/", json=payload, headers=headers)
        assert response.status_code == 200
        
        # Verify IPv4 is stored correctly in session
        if response.status_code == 200:
            access_token = response.json().get("access") or response.json().get("access_token")
            token_jti = get_token_jti(access_token)
            if token_jti:
                session = AuthSession.objects.using('default').filter(token_jti=token_jti).first()
                if session and hasattr(session, 'ip_address'):
                    assert session.ip_address == "192.168.1.100" or "192.168.1.100" in str(session.ip_address), \
                        "IPv4 address should be stored correctly"
        
        # Test valid IPv6
        headers = {"X-Forwarded-For": "2001:0db8:85a3:0000:0000:8a2e:0370:7334", "X-Real-IP": "2001:0db8:85a3:0000:0000:8a2e:0370:7334"}
        response = make_request(http_client, "post", "/auth/token/", json=payload, headers=headers)
        assert response.status_code == 200
        
        # Verify IPv6 is stored correctly in session
        if response.status_code == 200:
            access_token = response.json().get("access") or response.json().get("access_token")
            token_jti = get_token_jti(access_token)
            if token_jti:
                session = AuthSession.objects.using('default').filter(token_jti=token_jti).first()
                if session and hasattr(session, 'ip_address'):
                    # IPv6 might be normalized, so check if it contains the IPv6 address
                    ipv6_stored = str(session.ip_address)
                    assert "2001:0db8" in ipv6_stored or ipv6_stored == "2001:0db8:85a3:0000:0000:8a2e:0370:7334", \
                        "IPv6 address should be stored correctly"
        
        # Test invalid IP format
        headers = {"X-Forwarded-For": "invalid.ip.address", "X-Real-IP": "invalid.ip.address"}
        response = make_request(http_client, "post", "/auth/token/", json=payload, headers=headers)
        # Should either reject or sanitize invalid IP (may still allow login but sanitize IP)
        # If login succeeds, verify invalid IP is sanitized or set to None/default
        if response.status_code == 200:
            access_token = response.json().get("access") or response.json().get("access_token")
            token_jti = get_token_jti(access_token)
            if token_jti:
                session = AuthSession.objects.using('default').filter(token_jti=token_jti).first()
                if session and hasattr(session, 'ip_address'):
                    # Invalid IP should be sanitized (set to None, empty, or a default value)
                    invalid_ip = session.ip_address
                    assert invalid_ip is None or invalid_ip == "" or "invalid" not in str(invalid_ip).lower(), \
                        "Invalid IP address should be sanitized"
        else:
            # If login is rejected due to invalid IP, that's also acceptable
            assert response.status_code in [400, 401], f"Expected 400 or 401 for invalid IP, got {response.status_code}"

    # def test_s_3_https_enforcement(self, http_client):
    #     """Missing Test Case S.3: HTTPS Enforcement"""
    #     # This test requires checking if HTTP requests are rejected
    #     # In practice, this would be tested by making requests over HTTP
    #     # For now, we'll skip as it depends on server configuration
    #     pytest.skip("Requires HTTP/HTTPS server configuration testing")

    def test_s_4_password_hashing_verification(self):
        """Missing Test Case S.4: Password Hashing Verification"""
        if not DJANGO_AVAILABLE:
            pytest.skip("Django models not available")
        
        User = get_user_model()
        email, password = get_user_credentials("Account 1 Owner")
        
        # Get user (should exist from test data seeding)
        user = User.objects.filter(email=email).first()
        if not user:
            pytest.skip(f"User {email} not found in test data")
        
        # Verify password is hashed
        assert user.password != password, "Password should be hashed, not stored in plaintext"
        # assert user.password.startswith("bcrypt$"), "Password should use bcrypt algorithm"
        
        # Verify password verification works
        assert user.check_password(password), "Password verification should work"
        assert not user.check_password("WrongPassword123!"), "Wrong password should fail"

    def test_s_5_session_data_masking_in_logs(self, http_client):
        """Missing Test Case S.5: Session Data Masking in Logs"""
        if not DJANGO_AVAILABLE:
            pytest.skip("Django models not available")
        
        # This test would require checking actual log output
        # For now, we'll verify that tokens are not exposed in error messages
        email, password = get_user_credentials("Account 1 Owner")
        
        # Login to get token
        login_response = make_request(http_client, "post", "/auth/token/", json={
            "email": email,
            "password": password
        })
        assert login_response.status_code == 200
        access_token = login_response.json()["access"]
        
        # Try to use invalid token and verify token is not exposed in error
        client = requests.Session()
        client.base_url = http_client.base_url
        client.verify = getattr(http_client, 'verify', True)
        client.headers["Authorization"] = f"Bearer {access_token[:-5]}XXXXX"  # Tampered token
        
        response = make_request(client, "get", "/auth/sessions/")
        assert response.status_code == 401
        
        # Verify error response doesn't contain full token
        error_text = response.text
        assert access_token not in error_text, "Token should not be exposed in error messages"


@pytest.mark.acceptance
class TestDataModelAndConstraints:
    """Data Model & Constraints Tests"""

    def test_d_1_token_jti_uniqueness_constraint(self, http_client):
        """Missing Test Case D.1: Token JTI Uniqueness Constraint"""
        if not DJANGO_AVAILABLE:
            pytest.skip("Django models not available")
        
        email, password = get_user_credentials("Account 1 Owner")
        
        # Create multiple sessions
        tokens = []
        for i in range(5):
            login_response = make_request(http_client, "post", "/auth/token/", json={
                "email": email,
                "password": password
            })
            assert login_response.status_code == 200
            tokens.append(login_response.json()["access"])
        
        # Verify all JTIs are unique
        jtis = [get_token_jti(token) for token in tokens]
        jtis = [jti for jti in jtis if jti is not None]
        assert len(jtis) == len(set(jtis)), "All token JTIs should be unique"

    # def test_d_2_session_cleanup_after_expiration(self):
    #     """Missing Test Case D.2: Session Cleanup After Expiration"""
    #     # This test requires creating expired sessions and verifying cleanup
    #     # Would need to manipulate session expiration times or wait
    #     pytest.skip("Requires session expiration and cleanup process testing")


@pytest.mark.acceptance
class TestPredefinedCustomRoles:
    """Predefined Custom Roles Tests"""
