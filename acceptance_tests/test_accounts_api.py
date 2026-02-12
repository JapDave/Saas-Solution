"""
Acceptance tests for Account Management API endpoints.

These tests verify the actual HTTP API behavior end-to-end,
including authentication, authorization, and response formats.

Tests are organized by requirement (REQ-ACCOUNT-XXX) from:
- ACCOUNT-MANAGEMENT.md
- TEST_PLAN_ACCOUNT_MANAGEMENT.md
"""
import os
import pytest
import requests
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

# Import helpers from conftest
from acceptance_tests.conftest import (
    make_request,
    execute_raw_query,
    get_user_credentials,
    DJANGO_AVAILABLE,
)

# Import Django models if available
try:
    from django.db import connection, connections
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.utils import timezone
    from apps.accounts.models import Account
    from apps.users.models import User
    from apps.common.models import AuditLog, DataChangeLog
    from apps.subscriptions.models import Subscription
    DJANGO_AVAILABLE = True
except ImportError:
    raise ImportError("Django is not available")
    DJANGO_AVAILABLE = False
    User = None
    Account = None
    AuditLog = None
    DataChangeLog = None
    Subscription = None
    get_user_model = None
    connection = None
    connections = None
    settings = None
    timezone = None


@pytest.mark.acceptance
class TestREQAccount001CreateEnterpriseAccount:
    """REQ-ACCOUNT-001: Create Enterprise Account"""

    def test_1_1_successful_account_creation_by_saas_admin(self, authenticated_client, http_client):
        """Test Scenario 1.1: Successful Account Creation by SaaS Administrator"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        # time.sleep(3600)
        
        payload = {
            "name": "Acme Corporation",
            "description": "Enterprise customer account",
            "contact_email": f"admin{int(time.time())}@acmecorp.com"
        }
        
        start_time = time.time()
        response = make_request(client, "post", "/accounts/", json=payload)
        response_time = time.time() - start_time
        
        assert response.status_code == 201, f"Expected 201 but got {response.status_code}, response: {response.text}"
        data = response.json()
        
        # Verify response contains account details
        assert "uuid" in data or "id" in data, "Response should contain account identifier"
        assert data.get("name") == payload["name"], "Account name should match"
        assert data.get("contact_email") == payload["contact_email"], "Contact email should match"
        assert data.get("description") == payload["description"], "Description should match"
        assert data.get("is_active") is True, "Account should be active by default"
        assert "created_at" in data or "createdAt" in data, "Response should contain created_at"
        assert "updated_at" in data or "updatedAt" in data, "Response should contain updated_at"
        
        # Verify account exists in database
        if DJANGO_AVAILABLE and Account:
            account_uuid = data.get("uuid") or data.get("id")
            if account_uuid:
                account = Account.objects.using('default').filter(uuid=account_uuid).first()
                assert account is not None, "Account should exist in database"
                assert account.name == payload["name"], "Account name should match in database"
                assert account.contact_email == payload["contact_email"], "Contact email should match in database"
        
        # Verify response time
        assert response_time < 2.0, f"Response time should be less than 2 seconds, got {response_time:.2f}s"
        
        # Verify audit log entry is created
        if DJANGO_AVAILABLE and AuditLog:
            from django.utils import timezone
            before_request = timezone.now() - timedelta(seconds=5)
            user = User.objects.using('default').filter(email=email).first()
            account_uuid = data.get("uuid") or data.get("id")
            
            audit_log = AuditLog.objects.using('default').filter(
                path="/api/accounts/",
                method="POST",
                status_code=201,
                created_at__gte=before_request
            ).order_by("-created_at").first()
            assert audit_log is not None, "Audit log entry should be created"
            assert audit_log.success is True, "Audit log should mark success as True"
            assert audit_log.user_id == user.id, f"Audit log should mark the super admin as user, expected: {user.id}, got: {audit_log.user_id}"
            
            # Verify DataChangeLog for CREATE operation
            if DataChangeLog and account_uuid:
                data_change_log = DataChangeLog.objects.using('default').filter(
                    app_label="accounts",
                    model_name="Account",
                    action="create",
                    object_id=str(account_uuid),
                    created_at__gte=before_request
                ).order_by("-created_at").first()
                
                assert data_change_log is not None, "DataChangeLog entry should be created for CREATE"
                assert data_change_log.audit_log_id == audit_log.id, \
                    f"DataChangeLog audit_log_id should match AuditLog id: {data_change_log.audit_log_id} != {audit_log.id}"
                assert data_change_log.user_id == user.id, \
                    f"DataChangeLog user_id should match user: {data_change_log.user_id} != {user.id}"
                assert data_change_log.trace_id is not None, "DataChangeLog trace_id should not be null"
                assert data_change_log.span_id is not None, "DataChangeLog span_id should not be null"
                
                # Verify changed_fields contains expected fields
                changed_fields = data_change_log.changed_fields
                assert isinstance(changed_fields, dict), "changed_fields should be a dictionary"
                assert "name" in changed_fields, "changed_fields should contain 'name'"
                assert "uuid" in changed_fields or "contact_email" in changed_fields, "changed_fields should contain key fields"
                if "name" in changed_fields:
                    assert changed_fields["name"]["new"] == payload["name"], "Name should match payload"
                    assert changed_fields["name"]["old"] is None, "Old value should be None for CREATE"
                
                # Verify changed_fields_summary
                assert data_change_log.changed_fields_summary is not None, \
                    "changed_fields_summary should not be null"
                assert isinstance(data_change_log.changed_fields_summary, str), \
                    "changed_fields_summary should be a string"
                assert "name" in data_change_log.changed_fields_summary, \
                    "changed_fields_summary should contain 'name'"

    def test_1_2_account_creation_with_duplicate_name(self, authenticated_client, http_client):
        """Test Scenario 1.2: Account Creation with Duplicate Name"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Create first account
        payload1 = {
            "name": f"Duplicate Test Account {int(time.time())}",
            "contact_email": f"first{int(time.time())}@test.com"
        }
        response1 = make_request(client, "post", "/accounts/", json=payload1)
        assert response1.status_code == 201
        
        # Attempt to create account with duplicate name
        payload2 = {
            "name": payload1["name"],  # Same name
            "contact_email": f"second{int(time.time())}@test.com"
        }
        response2 = make_request(client, "post", "/accounts/", json=payload2)
        
        assert response2.status_code == 409, f"Expected 409 but got {response2.status_code}, response: {response2.text}"
        data = response2.json()
        assert "code" in data or "error" in data or "name" in str(data).lower(), \
            f"Response should indicate duplicate name, got {data}"
        assert data.get("code") == "ACCOUNT_NAME_EXISTS"
        if DJANGO_AVAILABLE and AuditLog:
            from django.utils import timezone
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path="/api/accounts/",
                method="POST",
                status_code=409,
                created_at__gte=timezone.now() - timedelta(seconds=5)
            ).order_by("-created_at").first()
            assert audit_log is not None, "Audit log entry should be created"
            assert audit_log.success is False, "Audit log should mark success as False"
            assert audit_log.user_id == user.id, f"Audit log should mark the super admin as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_1_3_account_creation_with_duplicate_contact_email(self, authenticated_client, http_client):
        """Test Scenario 1.3: Account Creation with Duplicate Contact Email"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Create first account
        unique_email = f"duplicate{int(time.time())}@test.com"
        payload1 = {
            "name": f"First Account {int(time.time())}",
            "contact_email": unique_email
        }
        response1 = make_request(client, "post", "/accounts/", json=payload1)
        assert response1.status_code == 201
        
        # Attempt to create account with duplicate email
        payload2 = {
            "name": f"Second Account {int(time.time())}",
            "contact_email": unique_email  # Same email
        }
        response2 = make_request(client, "post", "/accounts/", json=payload2)
        
        assert response2.status_code == 400, f"Expected 400 but got {response2.status_code}, response: {response2.text}"
        data = response2.json()
        assert "code" in data or "error" in data or "email" in str(data).lower(), \
            f"Response should indicate duplicate email, got {data}"
        assert data.get("code") == "CONTACT_EMAIL_EXISTS"
        
        if DJANGO_AVAILABLE and AuditLog:
            from django.utils import timezone
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path="/api/accounts/",
                method="POST",
                status_code=400,
                created_at__gte=timezone.now() - timedelta(seconds=5)
            ).order_by("-created_at").first()
            assert audit_log is not None, "Audit log entry should be created"
            assert audit_log.success is False, "Audit log should mark success as False"
            assert audit_log.user_id == user.id, f"Audit log should mark the super admin as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_1_4_account_creation_with_invalid_email_format(self, authenticated_client, http_client):
        """Test Scenario 1.4: Account Creation with Invalid Email Format"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        invalid_emails = [
            "notanemail",
            "missing@domain",
            "@nodomain.com",
            "",
            "a" * 250 + "@example.com"  # Exceeding 254 characters
        ]
        
        for invalid_email in invalid_emails:
            payload = {
                "name": f"Test Account {int(time.time())}",
                "contact_email": invalid_email
            }
            response = make_request(client, "post", "/accounts/", json=payload)
            assert response.status_code == 400, \
                f"Expected 400 for invalid email '{invalid_email}', got {response.status_code}, response: {response.text}"
            data = response.json()
            assert data.get('code') == "INVALID_ACCOUNT_DATA"

    def test_1_5_account_creation_with_invalid_name_length(self, authenticated_client, http_client):
        """Test Scenario 1.5: Account Creation with Invalid Name Length"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Test empty name
        payload1 = {
            "name": "",
            "contact_email": f"test{int(time.time())}@example.com"
        }
        response1 = make_request(client, "post", "/accounts/", json=payload1)
        assert response1.status_code == 400, \
            f"Expected 400 for empty name, got {response1.status_code}, response: {response1.text}"
        data1 = response1.json()
        assert data1.get("code") == "INVALID_ACCOUNT_DATA"
        if DJANGO_AVAILABLE and AuditLog:
            from django.utils import timezone
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path="/api/accounts/",
                method="POST",
                status_code=400,
                created_at__gte=timezone.now() - timedelta(seconds=5)
            ).order_by("-created_at").first()
            assert audit_log is not None, "Audit log entry should be created"
            assert audit_log.success is False, "Audit log should mark success as False"
            if user:
                assert audit_log.user_id == user.id, f"Audit log should mark the super admin as user, expected: {user.id}, got: {audit_log.user_id}"
        
        # Test name exceeding 100 characters
        long_name = "A" * 101
        payload2 = {
            "name": long_name,
            "contact_email": f"test{int(time.time())}@example.com"
        }
        response2 = make_request(client, "post", "/accounts/", json=payload2)
        assert response2.status_code == 400, \
            f"Expected 400 for name exceeding 100 chars, got {response2.status_code}, response: {response2.text}"
        data2 = response2.json()
        assert data2.get("code") == "INVALID_ACCOUNT_DATA"

    def test_1_6_account_creation_with_invalid_description_length(self, authenticated_client, http_client):
        """Test Scenario 1.6: Account Creation with Invalid Description Length"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Test description exceeding 500 characters
        long_description = "A" * 501
        payload = {
            "name": f"Test Account {int(time.time())}",
            "contact_email": f"test{int(time.time())}@example.com",
            "description": long_description
        }
        response = make_request(client, "post", "/accounts/", json=payload)
        assert response.status_code == 400, \
            f"Expected 400 for description exceeding 500 chars, got {response.status_code}, response: {response.text}"
        data = response.json()
        assert data.get("code") == "INVALID_ACCOUNT_DATA"
        if DJANGO_AVAILABLE and AuditLog:
            from django.utils import timezone
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path="/api/accounts/",
                method="POST",
                status_code=400,
                created_at__gte=timezone.now() - timedelta(seconds=5)
            ).order_by("-created_at").first()
            assert audit_log is not None, "Audit log entry should be created"
            assert audit_log.success is False, "Audit log should mark success as False"
            if user:
                assert audit_log.user_id == user.id, f"Audit log should mark the super admin as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_1_7_account_creation_without_required_fields(self, authenticated_client, http_client):
        """Test Scenario 1.7: Account Creation without Required Fields"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Test missing name
        payload1 = {
            "contact_email": f"test{int(time.time())}@example.com"
        }
        response1 = make_request(client, "post", "/accounts/", json=payload1)
        assert response1.status_code == 400, \
            f"Expected 400 for missing name, got {response1.status_code}, response: {response1.text}"
        data1 = response1.json()
        assert data1.get("code") == "INVALID_ACCOUNT_DATA"
        
        # Test missing contact_email
        payload2 = {
            "name": f"Test Account {int(time.time())}"
        }
        response2 = make_request(client, "post", "/accounts/", json=payload2)
        assert response2.status_code == 400, \
            f"Expected 400 for missing contact_email, got {response2.status_code}, response: {response2.text}"
        data2 = response2.json()
        assert data2.get("code") == "INVALID_ACCOUNT_DATA"
        
        # Test empty JSON body
        response3 = make_request(client, "post", "/accounts/", json={})
        assert response3.status_code == 400, \
            f"Expected 400 for empty body, got {response3.status_code}, response: {response3.text}"
        data3 = response3.json()
        assert data3.get("code") == "INVALID_ACCOUNT_DATA"

    def test_1_8_account_creation_by_unauthorized_user(self, authenticated_client, http_client):
        """Test Scenario 1.8: Account Creation by Unauthorized User"""
        # Try with Account Owner (should not have account:create permission)
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        payload = {
            "name": f"Unauthorized Test {int(time.time())}",
            "contact_email": f"unauthorized{int(time.time())}@test.com"
        }
        response = make_request(client, "post", "/accounts/", json=payload)
        
        assert response.status_code == 403, \
            f"Expected 403 for unauthorized user, got {response.status_code}, response: {response.text}"
        data = response.json()
        assert "code" in data or "permission" in str(data).lower() or "forbidden" in str(data).lower(), \
            f"Response should indicate insufficient permissions, got {data}"
        assert data.get("code") == "INSUFFICIENT_PERMISSIONS"
        if DJANGO_AVAILABLE and AuditLog:
            from django.utils import timezone
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path="/api/accounts/",
                method="POST",
                status_code=403,
                created_at__gte=timezone.now() - timedelta(seconds=5)
            ).order_by("-created_at").first()
            assert audit_log is not None, "Audit log entry should be created"
            assert audit_log.success is False, "Audit log should mark success as False"
            assert audit_log.user_id == user.id, f"Audit log should mark the super admin as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_1_9_account_creation_unauthenticated(self, http_client):
        """Test Scenario 1.9: Account Creation Unauthenticated"""
        payload = {
            "name": "Test Account",
            "contact_email": "test@example.com",
            "description": "Test description"
        }
        response = make_request(http_client, "post", "/accounts/", json=payload)
        
        assert response.status_code == 401, \
            f"Expected 401 for unauthenticated request, got {response.status_code}, response: {response.text}"
    
    def test_1_10_account_creation_by_unauthorized_user_Account_Manager(self, authenticated_client, http_client):
        """Test Scenario 1.10: Account Creation by Unauthorized User - Account Manager"""
        # Try with Account Owner (should not have account:create permission)
        email, password = get_user_credentials("SaaS Account Manager")
        client = authenticated_client(email, password)
        
        payload = {
            "name": f"Unauthorized Test {int(time.time())}",
            "contact_email": f"unauthorized{int(time.time())}@test.com"
        }
        response = make_request(client, "post", "/accounts/", json=payload)
        
        assert response.status_code == 403, \
            f"Expected 403 for unauthorized user, got {response.status_code}, response: {response.text}"
        data = response.json()
        assert "code" in data or "permission" in str(data).lower() or "forbidden" in str(data).lower(), \
            f"Response should indicate insufficient permissions, got {data}"
        assert data.get("code") == "INSUFFICIENT_PERMISSIONS"
        if DJANGO_AVAILABLE and AuditLog:
            from django.utils import timezone
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path="/api/accounts/",
                method="POST",
                status_code=403,
                created_at__gte=timezone.now() - timedelta(seconds=5)
            ).order_by("-created_at").first()
            assert audit_log is not None, "Audit log entry should be created"
            assert audit_log.success is False, "Audit log should mark success as False"
            assert audit_log.user_id == user.id, f"Audit log should mark the super admin as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_1_11_account_creation_rate_limiting(self, authenticated_client, http_client):
        """Test Scenario 1.11: Account Creation Rate Limiting (10 per hour per SaaS Admin)"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Create 10 accounts (should succeed)
        created_accounts = []
        for i in range(10):
            payload = {
                "name": f"Rate Limit Test Account {int(time.time())}_{i}",
                "contact_email": f"ratelimit{int(time.time())}_{i}@test.com"
            }
            response = make_request(client, "post", "/accounts/", json=payload)
            assert response.status_code == 201, \
                f"Account creation {i+1} should succeed, got {response.status_code}, response: {response.text}"
            created_accounts.append(response.json().get("uuid") or response.json().get("id"))
            time.sleep(0.1)  # Small delay to avoid race conditions
        
        # 11th attempt should be rate limited
        payload = {
            "name": f"Rate Limit Test Account {int(time.time())}_11",
            "contact_email": f"ratelimit{int(time.time())}_11@test.com"
        }
        response = make_request(client, "post", "/accounts/", json=payload)
        assert response.status_code == 429, \
            f"Expected 429 for rate limit exceeded, got {response.status_code}, response: {response.text}"
        data = response.json()
        assert data.get("code") == "RATE_LIMIT_EXCEEDED" or "rate limit" in str(data).lower(), \
            f"Response should indicate rate limit exceeded, got {data}"
        
        # Verify audit log for rate limited request
        if DJANGO_AVAILABLE and AuditLog:
            from django.utils import timezone
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path="/api/accounts/",
                method="POST",
                status_code=429,
                created_at__gte=timezone.now() - timedelta(seconds=5)
            ).order_by("-created_at").first()
            assert audit_log is not None, "Audit log entry should be created for rate limited request"
            assert audit_log.success is False, "Audit log should mark success as False for rate limited request"
            if user:
                assert audit_log.user_id == user.id, f"Audit log should mark the super admin as user, expected: {user.id}, got: {audit_log.user_id}"


@pytest.mark.acceptance
class TestREQAccount002RetrieveAccountInformation:
    """REQ-ACCOUNT-002: Retrieve Account Information"""

    def test_2_1_retrieve_account_by_saas_admin(self, authenticated_client, http_client):
        """Test Scenario 2.1: Retrieve Account by SaaS Administrator"""
        # Create an account first
        admin_email, admin_password = get_user_credentials("Super Admin")
        admin_client = authenticated_client(admin_email, admin_password)
        
        create_payload = {
            "name": f"Retrieve Test Account {int(time.time())}",
            "contact_email": f"retrieve{int(time.time())}@test.com"
        }
        create_response = make_request(admin_client, "post", "/accounts/", json=create_payload)
        assert create_response.status_code == 201
        account_uuid = create_response.json().get("uuid") or create_response.json().get("id")
        
        # Retrieve account
        start_time = time.time()
        response = make_request(admin_client, "get", f"/accounts/{account_uuid}/")
        response_time = time.time() - start_time
        
        assert response.status_code == 200, f"Expected 200 but got {response.status_code}, response: {response.text}"
        data = response.json()
        
        # Verify response contains account information
        assert data.get("name") == create_payload["name"], "Account name should match"
        assert data.get("contact_email") == create_payload["contact_email"], "Contact email should match"
        assert "uuid" in data or "id" in data, "Response should contain account identifier"
        assert "is_active" in data, "Response should contain is_active"
        assert "created_at" in data or "createdAt" in data, "Response should contain created_at"
        assert "updated_at" in data or "updatedAt" in data, "Response should contain updated_at"
        
        # Verify response time
        assert response_time < 0.5, f"Response time should be less than 500ms, got {response_time:.2f}s"
        if DJANGO_AVAILABLE and AuditLog:
            from django.utils import timezone
            user = User.objects.using('default').filter(email=admin_email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/accounts/{account_uuid}/",
                method="GET",
                status_code=200,
                created_at__gte=timezone.now() - timedelta(seconds=5)
            ).order_by("-created_at").first()
            assert audit_log is not None, "Audit log entry should be created"
            assert audit_log.success is True, "Audit log should mark success as True"
            assert audit_log.user_id == user.id, f"Audit log should mark the super admin as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_2_2_retrieve_own_account_by_account_owner(self, authenticated_client, http_client):
        """Test Scenario 2.2: Retrieve Own Account by Account Owner"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get account UUID from user's account
        if DJANGO_AVAILABLE and Account:
            User = get_user_model()
            user = User.objects.using('default').filter(email=email).first()
            if user:
                account_uuid = str(user.account.uuid)
                response = make_request(client, "get", f"/accounts/{account_uuid}/")
                assert response.status_code == 200, \
                    f"Expected 200 but got {response.status_code}, response: {response.text}"
                data = response.json()
                assert data.get("uuid") == str(user.account.uuid) or data.get("id") == user.account.id, \
                    "Account UUID should match"
                if DJANGO_AVAILABLE and AuditLog:
                    from django.utils import timezone
                    user = User.objects.using('default').filter(email=email).first()
                    audit_log = AuditLog.objects.using('default').filter(
                        path=f"/api/accounts/{account_uuid}/",
                        method="GET",
                        status_code=200,
                        created_at__gte=timezone.now() - timedelta(seconds=5)
                    ).order_by("-created_at").first()
                    assert audit_log is not None, "Audit log entry should be created"
                    assert audit_log.success is True, "Audit log should mark success as True"
                    assert audit_log.user_id == user.id, f"Audit log should mark the super admin as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_2_3_retrieve_account_by_account_admin(self, authenticated_client, http_client):
        """Test Scenario 2.3: Retrieve Account by Account Admin"""
        email, password = get_user_credentials("Account 1 Admin")
        client = authenticated_client(email, password)
        
        # Get account UUID from user's account
        if DJANGO_AVAILABLE and Account:
            User = get_user_model()
            user = User.objects.using('default').filter(email=email).first()
            assert user is not None, f"User should be found, email: {email}"
            account = user.account
            assert account is not None, f"Account should be found, user: {user.id}"
            response = make_request(client, "get", f"/accounts/{account.uuid}/")
            assert response.status_code == 200, \
                f"Expected 200 but got {response.status_code}, response: {response.text}"
            
            if DJANGO_AVAILABLE and AuditLog:
                from django.utils import timezone
                user = User.objects.using('default').filter(email=email).first()
                audit_log = AuditLog.objects.using('default').filter(
                    path=f"/api/accounts/{account.uuid}/",
                    method="GET",
                    status_code=200,
                    created_at__gte=timezone.now() - timedelta(seconds=5)
                ).order_by("-created_at").first()
                assert audit_log is not None, "Audit log entry should be created"
                assert audit_log.success is True, "Audit log should mark success as True"
                assert audit_log.user_id == user.id, f"Audit log should mark the super admin as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_2_4_retrieve_account_by_saas_account_manager_assigned(self, authenticated_client, http_client):
        """Test Scenario 2.4: Retrieve Account by SaaS Account Manager (Assigned Account)"""
        email, password = get_user_credentials("SaaS Account Manager")
        client = authenticated_client(email, password)
        
        # Get assigned account (Test Account Alpha or Test Account Gama)
        if DJANGO_AVAILABLE and Account:
            account = Account.objects.using('default').filter(name="Test Account Alpha").first()
            if account:
                response = make_request(client, "get", f"/accounts/{account.uuid}/")
                assert response.status_code == 200, \
                    f"Expected 200 but got {response.status_code}, response: {response.text}"
                if DJANGO_AVAILABLE and AuditLog:
                    from django.utils import timezone
                    user = User.objects.using('default').filter(email=email).first()
                    audit_log = AuditLog.objects.using('default').filter(
                        path=f"/api/accounts/{account.uuid}/",
                        method="GET",
                        status_code=200,
                        created_at__gte=timezone.now() - timedelta(seconds=5)
                    ).order_by("-created_at").first()
                    assert audit_log is not None, "Audit log entry should be created"
                    assert audit_log.success is True, "Audit log should mark success as True"
                    assert audit_log.user_id == user.id, f"Audit log should mark the super admin as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_2_5_retrieve_different_account_by_account_owner_unauthorized(self, authenticated_client, http_client):
        """Test Scenario 2.5: Retrieve Different Account by Account Owner (Unauthorized)"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Try to access Account 2 (owned by different user)
        if DJANGO_AVAILABLE and Account:
            account = Account.objects.using('default').filter(name="Test Account Beta").first()
            if account:
                response = make_request(client, "get", f"/accounts/{account.uuid}/")
                assert response.status_code == 403, \
                    f"Expected 403 for unauthorized access, got {response.status_code}, response: {response.text}"
                data = response.json()
                assert "code" in data or "permission" in str(data).lower() or "forbidden" in str(data).lower(), \
                    f"Response should indicate insufficient permissions, got {data}"
                assert data.get("code") == "INSUFFICIENT_PERMISSIONS"
                if DJANGO_AVAILABLE and AuditLog:
                    from django.utils import timezone
                    user = User.objects.using('default').filter(email=email).first()
                    audit_log = AuditLog.objects.using('default').filter(
                        path=f"/api/accounts/{account.uuid}/",
                        method="GET",
                        status_code=403,
                        created_at__gte=timezone.now() - timedelta(seconds=5)
                    ).order_by("-created_at").first()
                    assert audit_log is not None, "Audit log entry should be created"
                    assert audit_log.success is False, "Audit log should mark success as False"
                    if user:
                        assert audit_log.user_id == user.id, f"Audit log should mark the account owner as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_2_6_retrieve_account_by_saas_account_manager_unassigned(self, authenticated_client, http_client):
        """Test Scenario 2.6: Retrieve Account by SaaS Account Manager (Unassigned Account)"""
        email, password = get_user_credentials("SaaS Account Manager")
        client = authenticated_client(email, password)
        
        # Try to access Account Beta (not assigned to manager)
        if DJANGO_AVAILABLE and Account:
            account = Account.objects.using('default').filter(name="Test Account Beta").first()
            if account:
                response = make_request(client, "get", f"/accounts/{account.uuid}/")
                assert response.status_code == 403, \
                    f"Expected 403 for unassigned account, got {response.status_code}, response: {response.text}"
                data = response.json()
                assert data.get("code") == "INSUFFICIENT_PERMISSIONS"
                if DJANGO_AVAILABLE and AuditLog:
                    from django.utils import timezone
                    user = User.objects.using('default').filter(email=email).first()
                    audit_log = AuditLog.objects.using('default').filter(
                        path=f"/api/accounts/{account.uuid}/",
                        method="GET",
                        status_code=403,
                        created_at__gte=timezone.now() - timedelta(seconds=5)
                    ).order_by("-created_at").first()
                    assert audit_log is not None, "Audit log entry should be created"
                    assert audit_log.success is False, "Audit log should mark success as False"
                    if user:
                        assert audit_log.user_id == user.id, f"Audit log should mark the SaaS Account Manager as user, expected: {user.id}, got: {audit_log.user_id}"
                data = response.json()
                assert "code" in data or "permission" in str(data).lower() or "forbidden" in str(data).lower(), \
                    f"Response should indicate insufficient permissions, got {data}"
                assert data.get("code") == "INSUFFICIENT_PERMISSIONS"
                if DJANGO_AVAILABLE and AuditLog:
                    from django.utils import timezone
                    user = User.objects.using('default').filter(email=email).first()
                    audit_log = AuditLog.objects.using('default').filter(
                        path=f"/api/accounts/{account.uuid}/",
                        method="GET",
                        status_code=403,
                        created_at__gte=timezone.now() - timedelta(seconds=5)
                    ).order_by("-created_at").first()
                    assert audit_log is not None, "Audit log entry should be created"
                    assert audit_log.success is False, "Audit log should mark success as False"
                    assert audit_log.user_id == user.id, f"Audit log should mark the SaaS Account Manager as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_2_7_retrieve_nonexistent_account(self, authenticated_client, http_client):
        """Test Scenario 2.7: Retrieve Non-Existent Account"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Use a non-existent UUID
        fake_uuid = str(uuid.uuid4())
        response = make_request(client, "get", f"/accounts/{fake_uuid}/")
        
        assert response.status_code == 404, \
            f"Expected 404 for non-existent account, got {response.status_code}, response: {response.text}"
        data = response.json()
        assert "code" in data or "not found" in str(data).lower(), \
            f"Response should indicate account not found, got {data}"
        assert data.get("code") == "ACCOUNT_NOT_FOUND"
        if DJANGO_AVAILABLE and AuditLog:
            from django.utils import timezone
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path__startswith="/api/accounts/",
                method="GET",
                status_code=404,
                created_at__gte=timezone.now() - timedelta(seconds=5)
            ).order_by("-created_at").first()
            assert audit_log is not None, "Audit log entry should be created"
            assert audit_log.success is False, "Audit log should mark success as False"
            if user:
                assert audit_log.user_id == user.id, f"Audit log should mark the super admin as user, expected: {user.id}, got: {audit_log.user_id}"
        if DJANGO_AVAILABLE and AuditLog:
            from django.utils import timezone
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/accounts/{fake_uuid}/",
                method="GET",
                status_code=404,
                created_at__gte=timezone.now() - timedelta(seconds=5)
            ).order_by("-created_at").first()

            assert audit_log is not None, "Audit log entry should be created"
            assert audit_log.success is False, "Audit log should mark success as False"
            assert audit_log.user_id == user.id, f"Audit log should mark the super admin as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_2_8_retrieve_account_with_invalid_uuid_format(self, authenticated_client, http_client):
        """Test Scenario 2.9: Retrieve Account with Invalid UUID Format"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        invalid_uuids = ["invalid-uuid", "123", "not-a-uuid", ""]
        
        for invalid_uuid in invalid_uuids:
            response = make_request(client, "get", f"/accounts/{invalid_uuid}/")
            assert response.status_code in (400, 404, 500), \
                f"Expected 400 or 404 for invalid UUID '{invalid_uuid}', got {response.status_code}, response: {response.text}"

    def test_2_9_retrieve_account_unauthenticated(self, http_client):
        """Test Scenario 2.10: Retrieve Account Unauthenticated"""
        # Use a valid UUID format (even if it doesn't exist)
        account = None
        if DJANGO_AVAILABLE and Account:
            account = Account.objects.using('default').filter(name="Test Account Alpha").first()
        acc_uuid = account.uuid if account else str(uuid.uuid4())

        response = make_request(http_client, "get", f"/accounts/{acc_uuid}/")
        
        assert response.status_code == 401, \
            f"Expected 401 for unauthenticated request, got {response.status_code}, response: {response.text}"


@pytest.mark.acceptance
class TestREQAccount003UpdateAccountInformation:
    """REQ-ACCOUNT-003: Update Account Information"""

    def test_3_1_update_account_by_account_owner(self, authenticated_client, http_client):
        """Test Scenario 3.1: Update Account by Account Owner"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get account owned by this user
        if DJANGO_AVAILABLE and Account:
            User = get_user_model()
            user = User.objects.using('default').filter(email=email).first()
            if user:
                account = Account.objects.using('default').filter(created_by=user).first()
                if account:
                    original_name = account.name
                    original_description = account.description
                    
                    payload = {
                        "name": f"Updated Account Name {int(time.time())}",
                        "description": "Updated description",
                        "contact_email": account.contact_email  # Keep same email
                    }
                    
                    before_request = timezone.now() - timedelta(seconds=5)
                    response = make_request(client, "put", f"/accounts/{account.uuid}/", json=payload)
                    
                    assert response.status_code == 200, \
                        f"Expected 200 but got {response.status_code}, response: {response.text}"
                    data = response.json()
                    assert data.get("name") == payload["name"], "Account name should be updated"
                    assert data.get("description") == payload["description"], "Description should be updated"
                    
                    # Verify database state
                    account.refresh_from_db()
                    assert account.name == payload["name"], "Account name should be updated in database"
                    assert account.description == payload["description"], "Description should be updated in database"
                    
                    # Verify audit log
                    if DJANGO_AVAILABLE and AuditLog:
                        user = User.objects.using('default').filter(email=email).first()
                        audit_log = AuditLog.objects.using('default').filter(
                            path=f"/api/accounts/{account.uuid}/",
                            method="PUT",
                            status_code=200,
                            created_at__gte=before_request
                        ).order_by("-created_at").first()
                        assert audit_log is not None, "Audit log entry should be created"
                        assert audit_log.success is True, "Audit log should mark success as True"
                        if user:
                            assert audit_log.user_id == user.id, f"Audit log should mark the account owner as user, expected: {user.id}, got: {audit_log.user_id}"
                        
                        # Verify DataChangeLog for UPDATE operation
                        if DataChangeLog:
                            data_change_log = DataChangeLog.objects.using('default').filter(
                                app_label="accounts",
                                model_name="Account",
                                action="update",
                                object_id=str(account.uuid),
                                created_at__gte=before_request
                            ).order_by("-created_at").first()
                            
                            assert data_change_log is not None, "DataChangeLog entry should be created for UPDATE"
                            assert data_change_log.audit_log_id == audit_log.id, \
                                f"DataChangeLog audit_log_id should match AuditLog id: {data_change_log.audit_log_id} != {audit_log.id}"
                            assert data_change_log.user_id == user.id, \
                                f"DataChangeLog user_id should match user: {data_change_log.user_id} != {user.id}"
                            assert data_change_log.trace_id is not None, "DataChangeLog trace_id should not be null"
                            assert data_change_log.span_id is not None, "DataChangeLog span_id should not be null"
                            
                            # Verify changed_fields contains old and new values
                            changed_fields = data_change_log.changed_fields
                            assert isinstance(changed_fields, dict), "changed_fields should be a dictionary"
                            assert "name" in changed_fields, "changed_fields should contain 'name'"
                            if "name" in changed_fields:
                                assert changed_fields["name"]["old"] == original_name, \
                                    f"Old name should match original: {changed_fields['name']['old']} != {original_name}"
                                assert changed_fields["name"]["new"] == payload["name"], \
                                    f"New name should match payload: {changed_fields['name']['new']} != {payload['name']}"
                            
                            # Verify changed_fields_summary
                            assert data_change_log.changed_fields_summary is not None, \
                                "changed_fields_summary should not be null"
                            assert isinstance(data_change_log.changed_fields_summary, str), \
                                "changed_fields_summary should be a string"
                            assert "name" in data_change_log.changed_fields_summary, \
                                "changed_fields_summary should contain 'name'"

    def test_3_2_partial_update_account_by_account_admin(self, authenticated_client, http_client):
        """Test Scenario 3.2: Partial Update Account by Account Admin"""
        email, password = get_user_credentials("Account 1 Admin")
        client = authenticated_client(email, password)
        
        # Get account for this user
        if DJANGO_AVAILABLE and Account:
            User = get_user_model()
            user = User.objects.using('default').filter(email=email).first()
            if user:
                account = user.account
                if account:
                    # Use PATCH for partial update
                    payload = {
                        "description": f"Partially updated description {int(time.time())}"
                    }
                    response = make_request(client, "patch", f"/accounts/{account.uuid}/", json=payload)
                    
                    assert response.status_code == 200, \
                        f"Expected 200 but got {response.status_code}, response: {response.text}"
                    data = response.json()
                    assert data.get("description") == payload["description"], "Description should be updated"
                    if DJANGO_AVAILABLE and AuditLog:
                        from django.utils import timezone
                        user = User.objects.using('default').filter(email=email).first()
                        audit_log = AuditLog.objects.using('default').filter(
                            path=f"/api/accounts/{account.uuid}/",
                            method="PATCH",
                            status_code=200,
                            created_at__gte=timezone.now() - timedelta(seconds=5)
                        ).order_by("-created_at").first()
                        assert audit_log is not None, "Audit log entry should be created"
                        assert audit_log.success is True, "Audit log should mark success as True"
                        if user:
                            assert audit_log.user_id == user.id, f"Audit log should mark the account admin as user, expected: {user.id}, got: {audit_log.user_id}"
                    if DJANGO_AVAILABLE and AuditLog:
                        from django.utils import timezone
                        user = User.objects.using('default').filter(email=email).first()
                        audit_log = AuditLog.objects.using('default').filter(
                            path=f"/api/accounts/{account.uuid}/",
                            method="PATCH",
                            status_code=200,
                            created_at__gte=timezone.now() - timedelta(seconds=5)
                        ).order_by("-created_at").first()
                        assert audit_log is not None, "Audit log entry should be created"
                        assert audit_log.success is True, "Audit log should mark success as True"
                        assert audit_log.user_id == user.id, f"Audit log should mark the account admin as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_3_3_update_account_by_saas_account_manager(self, authenticated_client, http_client):
        """Test Scenario 3.3: Update Account by SaaS Account Manager (Assigned Account)"""
        email, password = get_user_credentials("SaaS Account Manager")
        client = authenticated_client(email, password)
        
        # Get assigned account
        if DJANGO_AVAILABLE and Account:
            account = Account.objects.using('default').filter(name="Test Account Alpha").first()
            if account:
                payload = {
                    "name": account.name,  # Keep same name
                    "description": f"Updated by manager {int(time.time())}",
                    "contact_email": account.contact_email
                }
                response = make_request(client, "put", f"/accounts/{account.uuid}/", json=payload)
                
                assert response.status_code == 200, \
                    f"Expected 200 but got {response.status_code}, response: {response.text}"
                if DJANGO_AVAILABLE and AuditLog:
                    from django.utils import timezone
                    user = User.objects.using('default').filter(email=email).first()
                    audit_log = AuditLog.objects.using('default').filter(
                        path=f"/api/accounts/{account.uuid}/",
                        method="PUT",
                        status_code=200,
                        created_at__gte=timezone.now() - timedelta(seconds=5)
                    ).order_by("-created_at").first()
                    assert audit_log is not None, "Audit log entry should be created"
                    assert audit_log.success is True, "Audit log should mark success as True"
                    assert audit_log.user_id == user.id, f"Audit log should mark the SaaS Account Manager as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_3_4_update_account_with_duplicate_name(self, authenticated_client, http_client):
        """Test Scenario 3.4: Update Account with Duplicate Name"""
        admin_email, admin_password = get_user_credentials("Super Admin")
        admin_client = authenticated_client(admin_email, admin_password)
        
        # Create two accounts
        timestamp = int(time.time())
        account1_payload = {
            "name": f"Account A {timestamp}",
            "contact_email": f"accounta{timestamp}@test.com"
        }
        account2_payload = {
            "name": f"Account B {timestamp}",
            "contact_email": f"accountb{timestamp}@test.com"
        }
        
        response1 = make_request(admin_client, "post", "/accounts/", json=account1_payload)
        assert response1.status_code == 201
        account1_uuid = response1.json().get("uuid") or response1.json().get("id")
        
        response2 = make_request(admin_client, "post", "/accounts/", json=account2_payload)
        assert response2.status_code == 201
        
        # Try to update Account A with Account B's name
        update_payload = {
            "name": account2_payload["name"],  # Duplicate name
            "contact_email": account1_payload["contact_email"]
        }
        update_response = make_request(admin_client, "put", f"/accounts/{account1_uuid}/", json=update_payload)
        
        assert update_response.status_code == 409, \
            f"Expected 409 for duplicate name, got {update_response.status_code}, response: {update_response.text}"
        data = update_response.json()
        assert data.get("code") == "ACCOUNT_NAME_EXISTS"
        if DJANGO_AVAILABLE and AuditLog:
            from django.utils import timezone
            user = User.objects.using('default').filter(email=admin_email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/accounts/{account1_uuid}/",
                method="PUT",
                status_code=409,
                created_at__gte=timezone.now() - timedelta(seconds=5)
            ).order_by("-created_at").first()

            assert audit_log is not None, "Audit log entry should be created"
            assert audit_log.success is False, "Audit log should mark success as False"
            assert audit_log.user_id == user.id, f"Audit log should mark the super admin as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_3_5_update_account_with_duplicate_contact_email(self, authenticated_client, http_client):
        """Test Scenario 3.5: Update Account with Duplicate Contact Email"""
        admin_email, admin_password = get_user_credentials("Super Admin")
        admin_client = authenticated_client(admin_email, admin_password)
        
        # Create two accounts
        timestamp = int(time.time())
        account1_payload = {
            "name": f"Account A {timestamp}",
            "contact_email": f"accounta{timestamp}@test.com"
        }
        account2_payload = {
            "name": f"Account B {timestamp}",
            "contact_email": f"accountb{timestamp}@test.com"
        }
        
        response1 = make_request(admin_client, "post", "/accounts/", json=account1_payload)
        assert response1.status_code == 201
        account1_uuid = response1.json().get("uuid") or response1.json().get("id")
        
        response2 = make_request(admin_client, "post", "/accounts/", json=account2_payload)
        assert response2.status_code == 201
        
        # Try to update Account A with Account B's email
        update_payload = {
            "name": account1_payload["name"],
            "contact_email": account2_payload["contact_email"]  # Duplicate email
        }
        update_response = make_request(admin_client, "put", f"/accounts/{account1_uuid}/", json=update_payload)
        
        assert update_response.status_code == 400, \
            f"Expected 400 for duplicate email, got {update_response.status_code}, response: {update_response.text}"
        data = update_response.json()
        assert data.get("code") == "CONTACT_EMAIL_EXISTS"
        if DJANGO_AVAILABLE and AuditLog:
            from django.utils import timezone
            user = User.objects.using('default').filter(email=admin_email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/accounts/{account1_uuid}/",
                method="PUT",
                status_code=400,
                created_at__gte=timezone.now() - timedelta(seconds=5)
            ).order_by("-created_at").first()
            assert audit_log is not None, "Audit log entry should be created"
            assert audit_log.success is False, "Audit log should mark success as False"
            assert audit_log.user_id == user.id, f"Audit log should mark the super admin as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_3_6_update_account_by_unauthorized_user(self, authenticated_client, http_client):
        """Test Scenario 3.6: Update Account by Unauthorized User"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Try to update Account 2 (owned by different user)
        if DJANGO_AVAILABLE and Account:
            account = Account.objects.using('default').filter(name="Test Account Beta").first()
            if account:
                payload = {
                    "name": account.name,
                    "contact_email": account.contact_email
                }
                response = make_request(client, "put", f"/accounts/{account.uuid}/", json=payload)
                
                assert response.status_code == 403, \
                    f"Expected 403 for unauthorized update, got {response.status_code}, response: {response.text}"
                data = response.json()
                assert data.get("code") == "INSUFFICIENT_PERMISSIONS"
                if DJANGO_AVAILABLE and AuditLog:
                    from django.utils import timezone
                    user = User.objects.using('default').filter(email=email).first()
                    audit_log = AuditLog.objects.using('default').filter(
                        path=f"/api/accounts/{account.uuid}/",
                        method="PUT",
                        status_code=403,
                        created_at__gte=timezone.now() - timedelta(seconds=5)
                    ).order_by("-created_at").first()

                    assert audit_log is not None, "Audit log entry should be created"
                    assert audit_log.success is False, "Audit log should mark success as False"
                    assert audit_log.user_id == user.id, f"Audit log should mark the account owner as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_3_7_update_account_with_invalid_data(self, authenticated_client, http_client):
        """Test Scenario 3.7: Update Account with Invalid Data"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get account owned by this user
        if DJANGO_AVAILABLE and Account:
            User = get_user_model()
            user = User.objects.using('default').filter(email=email).first()
            if user:
                account = Account.objects.using('default').filter(created_by=user).first()
                if account:
                    # Test invalid email format
                    invalid_payload = {
                        "name": account.name,
                        "contact_email": "invalid-email-format"
                    }
                    response = make_request(client, "put", f"/accounts/{account.uuid}/", json=invalid_payload)
                    assert response.status_code == 400, \
                        f"Expected 400 for invalid email, got {response.status_code}, response: {response.text}"
                    data = response.json()
                    assert data.get("code") == "INVALID_CONTACT_EMAIL"
                    if DJANGO_AVAILABLE and AuditLog:
                        from django.utils import timezone
                        user = User.objects.using('default').filter(email=email).first()
                        audit_log = AuditLog.objects.using('default').filter(
                            path=f"/api/accounts/{account.uuid}/",
                            method="PUT",
                            status_code=400,
                            created_at__gte=timezone.now() - timedelta(seconds=5)
                        ).order_by("-created_at").first()
                        assert audit_log is not None, "Audit log entry should be created"
                        assert audit_log.success is False, "Audit log should mark success as False"
                        assert audit_log.user_id == user.id, f"Audit log should mark the account owner as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_3_8_account_update_rate_limiting(self, authenticated_client, http_client):
        """Test Scenario 3.8: Account Update Rate Limiting (100 per hour per user)"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get account owned by this user
        if DJANGO_AVAILABLE and Account:
            User = get_user_model()
            user = User.objects.using('default').filter(email=email).first()
            if user:
                account = Account.objects.using('default').filter(created_by=user).first()
                if account:
                    # Perform 100 updates (should succeed)
                    for i in range(100):
                        payload = {
                            "name": account.name,  # Keep same name
                            "description": f"Rate limit test update {i}",
                            "contact_email": account.contact_email
                        }
                        response = make_request(client, "put", f"/accounts/{account.uuid}/", json=payload)
                        assert response.status_code == 200, \
                            f"Update {i+1} should succeed, got {response.status_code}, response: {response.text}"
                        time.sleep(0.01)  # Small delay to avoid race conditions
                    
                    # 101st attempt should be rate limited
                    payload = {
                        "name": account.name,
                        "description": "Rate limit test update 101",
                        "contact_email": account.contact_email
                    }
                    response = make_request(client, "put", f"/accounts/{account.uuid}/", json=payload)
                    assert response.status_code == 429, \
                        f"Expected 429 for rate limit exceeded, got {response.status_code}, response: {response.text}"
                    data = response.json()
                    assert data.get("code") == "RATE_LIMIT_EXCEEDED" or "rate limit" in str(data).lower(), \
                        f"Response should indicate rate limit exceeded, got {data}"


@pytest.mark.acceptance
class TestREQAccount004DeactivateAccount:
    """REQ-ACCOUNT-004: Deactivate Account"""

    def test_4_1_deactivate_account_by_saas_account_manager_no_subscriptions(self, authenticated_client, http_client):
        """Test Scenario 4.1: Deactivate Account by SaaS Account Manager (No Active Subscriptions)"""
        email, password = get_user_credentials("SaaS Account Manager")
        client = authenticated_client(email, password)
        
        # Get assigned account (should have no active subscriptions)
        if DJANGO_AVAILABLE and Account:
            account = Account.objects.using('default').filter(name="Test Account Gama").first()
            if account:
                # Ensure account is active
                account.is_active = True
                account.save()
                
                response = make_request(client, "post", f"/accounts/{account.uuid}/deactivate/")
                
                assert response.status_code == 200, \
                    f"Expected 200 but got {response.status_code}, response: {response.text}"
                data = response.json()
                assert data.get("is_active") is False, "Account should be deactivated"
                
                # Verify in database
                account.refresh_from_db()
                assert account.is_active is False, "Account should be inactive in database"
                
                # Verify audit log
                if DJANGO_AVAILABLE and AuditLog:
                    from django.utils import timezone
                    user = User.objects.using('default').filter(email=email).first()
                    audit_log = AuditLog.objects.using('default').filter(
                        path=f"/api/accounts/{account.uuid}/deactivate/",
                        method="POST",
                        status_code=200,
                        created_at__gte=timezone.now() - timedelta(seconds=5)
                    ).order_by("-created_at").first()
                    assert audit_log is not None, "Audit log entry should be created"
                    assert audit_log.success is True, "Audit log should mark success as True"
                    if user:
                        assert audit_log.user_id == user.id, f"Audit log should mark the SaaS Account Manager as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_4_2_deactivate_account_with_active_subscriptions_rejected(self, authenticated_client, http_client):
        """Test Scenario 4.2: Deactivate Account with Active Subscriptions (Rejected)"""
        email, password = get_user_credentials("SaaS Account Manager")
        client = authenticated_client(email, password)
        
        # Get account with active subscriptions (Test Account Alpha)
        if DJANGO_AVAILABLE and Account:
            account = Account.objects.using('default').filter(name="Test Account Alpha").first()
            if account:
                # Check if account has active subscriptions
                has_active_subscriptions = False
                if Subscription:
                    has_active_subscriptions = Subscription.objects.using('default').filter(
                        organization__account=account,
                        is_active=True
                    ).exists()
                assert has_active_subscriptions, "Account should have active subscriptions"
                if has_active_subscriptions:
                    response = make_request(client, "post", f"/accounts/{account.uuid}/deactivate/")
                    assert response.status_code == 409, \
                        f"Expected 409 for account with active subscriptions, got {response.status_code}, response: {response.text}"
                    data = response.json()
                    assert "subscription" in str(data).lower() or "code" in data, \
                        f"Response should indicate active subscriptions, got {data}"
                    assert data.get("code") == "ACCOUNT_HAS_ACTIVE_SUBSCRIPTIONS"
                    if DJANGO_AVAILABLE and AuditLog:
                        from django.utils import timezone
                        user = User.objects.using('default').filter(email=email).first()
                        audit_log = AuditLog.objects.using('default').filter(
                            path=f"/api/accounts/{account.uuid}/deactivate/",
                            method="POST",
                            status_code=400,
                            created_at__gte=timezone.now() - timedelta(seconds=5)
                        ).order_by("-created_at").first()
                        assert audit_log is not None, "Audit log entry should be created"
                        assert audit_log.success is False, "Audit log should mark success as False"
                        if user:
                            assert audit_log.user_id == user.id, f"Audit log should mark the SaaS Account Manager as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_4_3_deactivate_account_by_saas_admin_bypass_subscription_check(self, authenticated_client, http_client):
        """Test Scenario 4.3: Deactivate Account by SaaS Administrator (Bypass Subscription Check)"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Create account with active subscriptions (if possible) or use existing
        if DJANGO_AVAILABLE and Account:
            account = Account.objects.using('default').filter(name="Test Account Alpha").first()
            if account:
                # Ensure account is active
                account.is_active = True
                account.save()
                
                response = make_request(client, "post", f"/accounts/{account.uuid}/deactivate/")
                
                # SaaS Admin should be able to deactivate regardless of subscriptions
                assert response.status_code == 200, \
                    f"Expected 200 for SaaS Admin, got {response.status_code}, response: {response.text}"
                data = response.json()
                assert data.get("is_active") is False, "Account should be deactivated"
                if DJANGO_AVAILABLE and AuditLog:
                    from django.utils import timezone
                    user = User.objects.using('default').filter(email=email).first()
                    audit_log = AuditLog.objects.using('default').filter(
                        path=f"/api/accounts/{account.uuid}/deactivate/",
                        method="POST",
                        status_code=200,
                        created_at__gte=timezone.now() - timedelta(seconds=5)
                    ).order_by("-created_at").first()
                    assert audit_log is not None, "Audit log entry should be created"
                    assert audit_log.success is True, "Audit log should mark success as True"
                    if user:
                        assert audit_log.user_id == user.id, f"Audit log should mark the super admin as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_4_4_deactivate_already_inactive_account(self, authenticated_client, http_client):
        """Test Scenario 4.4: Deactivate Already Inactive Account"""
        email, password = get_user_credentials("SaaS Account Manager")
        client = authenticated_client(email, password)
        
        # Get account and ensure it's inactive
        if DJANGO_AVAILABLE and Account:
            account = Account.objects.using('default').filter(name="Test Account Gama").first()
            if account:
                account.is_active = False
                account.save()
                
                response = make_request(client, "post", f"/accounts/{account.uuid}/deactivate/")
                
                # Should handle gracefully (200 OK for idempotent behavior or 400)
                assert response.status_code in (200, 400), \
                    f"Expected 200 or 400 for already inactive account, got {response.status_code}, response: {response.text}"

    def test_4_5_deactivate_account_by_unauthorized_user(self, authenticated_client, http_client):
        """Test Scenario 4.5: Deactivate Account by Unauthorized User"""
        email, password = get_user_credentials("Account 1 Admin")
        client = authenticated_client(email, password)
        
        # Account Admin should not be able to deactivate
        if DJANGO_AVAILABLE and Account:
            account = Account.objects.using('default').filter(name="Test Account Alpha").first()
            if account:
                response = make_request(client, "post", f"/accounts/{account.uuid}/deactivate/")
                
                assert response.status_code == 403, \
                    f"Expected 403 for unauthorized deactivation, got {response.status_code}, response: {response.text}"
                data = response.json()
                assert data.get("code") == "INSUFFICIENT_PERMISSIONS"
                if DJANGO_AVAILABLE and AuditLog:
                    from django.utils import timezone
                    user = User.objects.using('default').filter(email=email).first()
                    audit_log = AuditLog.objects.using('default').filter(
                        path=f"/api/accounts/{account.uuid}/deactivate/",
                        method="POST",
                        status_code=403,
                        created_at__gte=timezone.now() - timedelta(seconds=5)
                    ).order_by("-created_at").first()
                    assert audit_log is not None, "Audit log entry should be created"
                    assert audit_log.success is False, "Audit log should mark success as False"
                    if user:
                        assert audit_log.user_id == user.id, f"Audit log should mark the account admin as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_4_6_deactivate_nonexistent_account(self, authenticated_client, http_client):
        """Test Scenario 4.6: Deactivate Non-Existent Account"""
        email, password = get_user_credentials("SaaS Account Manager")
        client = authenticated_client(email, password)
        
        fake_uuid = str(uuid.uuid4())
        response = make_request(client, "post", f"/accounts/{fake_uuid}/deactivate/")
        
        assert response.status_code in (404, 403), \
            f"Expected 404 or 403 for non-existent account, got {response.status_code}, response: {response.text}"


@pytest.mark.acceptance
class TestREQAccount005DeleteAccount:
    """REQ-ACCOUNT-005: Delete Account (Soft Delete)"""

    def test_5_1_delete_account_by_saas_account_manager_no_subscriptions(self, authenticated_client, http_client):
        """Test Scenario 5.1: Delete Account by SaaS Account Manager (No Active Subscriptions)"""
        email, password = get_user_credentials("SaaS Account Manager")
        client = authenticated_client(email, password)
        
        # Create a temporary account for deletion
        admin_email, admin_password = get_user_credentials("Super Admin")
        admin_client = authenticated_client(admin_email, admin_password)
        
        timestamp = int(time.time())
        create_payload = {
            "name": f"Delete Test Account {timestamp}",
            "contact_email": f"deletetest{timestamp}@test.com"
        }
        create_response = make_request(admin_client, "post", "/accounts/", json=create_payload)
        assert create_response.status_code == 201
        account_uuid = create_response.json().get("uuid") or create_response.json().get("id")
        
        # Assign account to SaaS Account Manager (if needed)
        # For now, try to delete with SaaS Account Manager
        # Note: This might fail if account assignment is required
        
        # Delete account
        response = make_request(client, "delete", f"/accounts/{account_uuid}/")
        
        # Should succeed if account is assigned, or 403 if not assigned
        assert response.status_code in (204, 403), \
            f"Expected 204 or 403, got {response.status_code}, response: {response.text}"
        
        if response.status_code == 204:
            # Verify soft delete in database
            if DJANGO_AVAILABLE and Account:
                account = Account.objects.using('default').filter(uuid=account_uuid).first()
                if account:
                    assert account.deleted_at is not None, "Account should have deleted_at set"

    def test_5_2_delete_account_with_active_subscriptions_rejected(self, authenticated_client, http_client):
        """Test Scenario 5.2: Delete Account with Active Subscriptions (Rejected)"""
        email, password = get_user_credentials("SaaS Account Manager")
        client = authenticated_client(email, password)
        
        # Get account with active subscriptions
        if DJANGO_AVAILABLE and Account:
            account = Account.objects.using('default').filter(name="Test Account Alpha").first()
            if account:
                has_active_subscriptions = False
                if Subscription:
                    has_active_subscriptions = Subscription.objects.using('default').filter(
                        organization__account=account,
                        is_active=True
                    ).exists()
                
                if has_active_subscriptions:
                    response = make_request(client, "delete", f"/accounts/{account.uuid}/")
                    assert response.status_code in (400, 409, 403), \
                        f"Expected 400, 409, or 403 for account with active subscriptions, got {response.status_code}, response: {response.text}"
                    data = response.json()
                    assert data.get("code") == "ACCOUNT_HAS_ACTIVE_SUBSCRIPTIONS"
                    if DJANGO_AVAILABLE and AuditLog:
                        from django.utils import timezone
                        user = User.objects.using('default').filter(email=email).first()
                        audit_log = AuditLog.objects.using('default').filter(
                            path=f"/api/accounts/{account.uuid}/",
                            method="DELETE",
                            status_code=response.status_code,
                            created_at__gte=timezone.now() - timedelta(seconds=5)
                        ).order_by("-created_at").first()
                        assert audit_log is not None, "Audit log entry should be created"
                        assert audit_log.success is False, "Audit log should mark success as False"
                        if user:
                            assert audit_log.user_id == user.id, f"Audit log should mark the SaaS Account Manager as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_5_3_delete_account_by_saas_admin_bypass_subscription_check(self, authenticated_client, http_client):
        """Test Scenario 5.3: Delete Account by SaaS Administrator (Bypass Subscription Check)"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Create account for deletion
        timestamp = int(time.time())
        create_payload = {
            "name": f"Admin Delete Test {timestamp}",
            "contact_email": f"admindelete{timestamp}@test.com"
        }
        create_response = make_request(client, "post", "/accounts/", json=create_payload)
        assert create_response.status_code == 201
        account_uuid = create_response.json().get("uuid") or create_response.json().get("id")
        
        # Delete account
        before_request = timezone.now() - timedelta(seconds=5)
        response = make_request(client, "delete", f"/accounts/{account_uuid}/")
        
        assert response.status_code == 204, \
            f"Expected 204 for SaaS Admin deletion, got {response.status_code}, response: {response.text}"
        
        # Verify soft delete in database
        if DJANGO_AVAILABLE and Account:
            account = Account.objects.using('default').filter(uuid=account_uuid).first()
            if account:
                assert account.deleted_at is not None, "Account should have deleted_at set"
        
        # Verify audit log
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/accounts/{account_uuid}/",
                method="DELETE",
                status_code=204,
                created_at__gte=before_request
            ).order_by("-created_at").first()
            assert audit_log is not None, "Audit log entry should be created"
            assert audit_log.success is True, "Audit log should mark success as True"
            if user:
                assert audit_log.user_id == user.id, f"Audit log should mark the super admin as user, expected: {user.id}, got: {audit_log.user_id}"
            
            # Verify DataChangeLog for DELETE operation
            if DataChangeLog:
                data_change_log = DataChangeLog.objects.using('default').filter(
                    app_label="accounts",
                    model_name="Account",
                    action="delete",
                    object_id=str(account_uuid),
                    created_at__gte=before_request
                ).order_by("-created_at").first()
                
                assert data_change_log is not None, "DataChangeLog entry should be created for DELETE"
                assert data_change_log.audit_log_id == audit_log.id, \
                    f"DataChangeLog audit_log_id should match AuditLog id: {data_change_log.audit_log_id} != {audit_log.id}"
                assert data_change_log.user_id == user.id, \
                    f"DataChangeLog user_id should match user: {data_change_log.user_id} != {user.id}"
                assert data_change_log.trace_id is not None, "DataChangeLog trace_id should not be null"
                assert data_change_log.span_id is not None, "DataChangeLog span_id should not be null"
                
                # Verify changed_fields contains deleted_at
                changed_fields = data_change_log.changed_fields
                assert isinstance(changed_fields, dict), "changed_fields should be a dictionary"
                assert "deleted_at" in changed_fields, "changed_fields should contain 'deleted_at' for DELETE"
                if "deleted_at" in changed_fields:
                    assert changed_fields["deleted_at"]["old"] is None, "Old deleted_at should be None"
                    assert changed_fields["deleted_at"]["new"] is not None, "New deleted_at should be set"
                
                # Verify changed_fields_summary
                assert data_change_log.changed_fields_summary is not None, \
                    "changed_fields_summary should not be null"
                assert "deleted_at" in data_change_log.changed_fields_summary, \
                    "changed_fields_summary should contain 'deleted_at'"

    def test_5_4_access_deleted_account(self, authenticated_client, http_client):
        """Test Scenario 5.4: Access Deleted Account"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Create and delete account
        timestamp = int(time.time())
        create_payload = {
            "name": f"Access Deleted Test {timestamp}",
            "contact_email": f"accessdeleted{timestamp}@test.com"
        }
        create_response = make_request(client, "post", "/accounts/", json=create_payload)
        assert create_response.status_code == 201
        account_uuid = create_response.json().get("uuid") or create_response.json().get("id")
        
        # Delete account
        delete_response = make_request(client, "delete", f"/accounts/{account_uuid}/")
        assert delete_response.status_code == 204
        
        # Try to access deleted account
        get_response = make_request(client, "get", f"/accounts/{account_uuid}/")
        assert get_response.status_code == 404, \
            f"Expected 404 for deleted account, got {get_response.status_code}, response: {get_response.text}"
        data = get_response.json()
        assert data.get("code") == "ACCOUNT_NOT_FOUND"

    def test_5_5_delete_account_by_unauthorized_user(self, authenticated_client, http_client):
        """Test Scenario 5.5: Delete Account by Unauthorized User"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Account Owner should not be able to delete
        if DJANGO_AVAILABLE and Account:
            account = Account.objects.using('default').filter(name="Test Account Alpha").first()
            if account:
                response = make_request(client, "delete", f"/accounts/{account.uuid}/")
                
                assert response.status_code == 403, \
                    f"Expected 403 for unauthorized deletion, got {response.status_code}, response: {response.text}"
                data = response.json()
                assert data.get("code") == "INSUFFICIENT_PERMISSIONS"
                if DJANGO_AVAILABLE and AuditLog:
                    from django.utils import timezone
                    user = User.objects.using('default').filter(email=email).first()
                    audit_log = AuditLog.objects.using('default').filter(
                        path=f"/api/accounts/{account.uuid}/",
                        method="DELETE",
                        status_code=403,
                        created_at__gte=timezone.now() - timedelta(seconds=5)
                    ).order_by("-created_at").first()
                    assert audit_log is not None, "Audit log entry should be created"
                    assert audit_log.success is False, "Audit log should mark success as False"
                    if user:
                        assert audit_log.user_id == user.id, f"Audit log should mark the account owner as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_5_6_delete_nonexistent_account_by_account_manager(self, authenticated_client, http_client):
        """Test Scenario 5.6: Delete Non-Existent Account"""
        email, password = get_user_credentials("SaaS Account Manager")
        client = authenticated_client(email, password)
        
        fake_uuid = str(uuid.uuid4())
        response = make_request(client, "delete", f"/accounts/{fake_uuid}/")
        
        assert response.status_code == 403, \
            f"Expected 403 for non-existent account, got {response.status_code}, response: {response.text}"

    def test_5_6_delete_nonexistent_account_by_admin(self, authenticated_client, http_client):
        """Test Scenario 5.6: Delete Non-Existent Account"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        fake_uuid = str(uuid.uuid4())
        response = make_request(client, "delete", f"/accounts/{fake_uuid}/")
        
        assert response.status_code == 404, \
            f"Expected 404 for non-existent account, got {response.status_code}, response: {response.text}"

    def test_5_7_account_deletion_rate_limiting(self, authenticated_client, http_client):
        """Test Scenario 5.7: Account Deletion Rate Limiting (5 per day per SaaS Admin)"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Create and delete 5 accounts (should succeed)
        deleted_accounts = []
        for i in range(5):
            # Create account
            create_payload = {
                "name": f"Delete Rate Limit Test {int(time.time())}_{i}",
                "contact_email": f"deleteratelimit{int(time.time())}_{i}@test.com"
            }
            create_response = make_request(client, "post", "/accounts/", json=create_payload)
            assert create_response.status_code == 201, \
                f"Account creation {i+1} should succeed, got {create_response.status_code}"
            account_uuid = create_response.json().get("uuid") or create_response.json().get("id")
            
            # Delete account
            delete_response = make_request(client, "delete", f"/accounts/{account_uuid}/")
            assert delete_response.status_code == 204, \
                f"Account deletion {i+1} should succeed, got {delete_response.status_code}"
            deleted_accounts.append(account_uuid)
            time.sleep(0.1)  # Small delay to avoid race conditions
        
        # 6th deletion attempt should be rate limited
        # Create account for 6th deletion
        create_payload = {
            "name": f"Delete Rate Limit Test {int(time.time())}_6",
            "contact_email": f"deleteratelimit{int(time.time())}_6@test.com"
        }
        create_response = make_request(client, "post", "/accounts/", json=create_payload)
        assert create_response.status_code == 201, "Account creation should succeed"
        account_uuid = create_response.json().get("uuid") or create_response.json().get("id")
        
        # Attempt 6th deletion
        delete_response = make_request(client, "delete", f"/accounts/{account_uuid}/")
        assert delete_response.status_code == 429, \
            f"Expected 429 for rate limit exceeded, got {delete_response.status_code}, response: {delete_response.text}"
        data = delete_response.json()
        assert data.get("code") == "RATE_LIMIT_EXCEEDED" or "rate limit" in str(data).lower(), \
            f"Response should indicate rate limit exceeded, got {data}"


@pytest.mark.acceptance
class TestREQAccount006ListAccountsWithPagination:
    """REQ-ACCOUNT-006: List Accounts with Pagination"""

    def test_6_1_list_all_accounts_by_saas_admin(self, authenticated_client, http_client):
        """Test Scenario 6.1: List All Accounts by SaaS Administrator"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        start_time = time.time()
        response = make_request(client, "get", "/accounts/")
        response_time = time.time() - start_time
        
        assert response.status_code == 200, f"Expected 200 but got {response.status_code}, response: {response.text}"
        data = response.json()
        
        # Verify paginated structure
        assert "results" in data or isinstance(data, list), "Response should contain results or be a list"
        assert response_time < 1.0, f"Response time should be less than 1 second, got {response_time:.2f}s"
        
        # If paginated, verify pagination fields
        if isinstance(data, dict):
            assert "count" in data or "results" in data, "Paginated response should have count or results"
            if "results" in data:
                assert isinstance(data["results"], list), "Results should be a list"
        if DJANGO_AVAILABLE and AuditLog:
            from django.utils import timezone
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path="/api/accounts/",
                method="GET",
                status_code=200,
                created_at__gte=timezone.now() - timedelta(seconds=5)
            ).order_by("-created_at").first()
            assert audit_log is not None, "Audit log entry should be created"
            assert audit_log.success is True, "Audit log should mark success as True"
            if user:
                assert audit_log.user_id == user.id, f"Audit log should mark the super admin as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_6_2_list_accounts_by_saas_account_manager_assigned_only(self, authenticated_client, http_client):
        """Test Scenario 6.2: List Accounts by SaaS Account Manager (Assigned Only)"""
        email, password = get_user_credentials("SaaS Account Manager")
        client = authenticated_client(email, password)
        
        response = make_request(client, "get", "/accounts/")
        assert response.status_code == 200, f"Expected 200 but got {response.status_code}, response: {response.text}"
        data = response.json()
        
        # Get results (handle both paginated and non-paginated responses)
        if isinstance(data, dict) and "results" in data:
            accounts = data["results"]
        elif isinstance(data, list):
            accounts = data
        else:
            accounts = []
        
        # Verify only assigned accounts are returned
        # SaaS Account Manager should only see Test Account Alpha and Test Account Gama
        account_names = [acc.get("name") for acc in accounts]
        assert "Test Account Alpha" in account_names or "Test Account Gama" in account_names, \
            "Should see at least one assigned account"
        
        # Should not see Test Account Beta (not assigned)
        assert "Test Account Beta" not in account_names, \
            "Should not see unassigned accounts"
        if DJANGO_AVAILABLE and AuditLog:
            from django.utils import timezone
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path="/api/accounts/",
                method="GET",
                status_code=200,
                created_at__gte=timezone.now() - timedelta(seconds=5)
            ).order_by("-created_at").first()
            assert audit_log is not None, "Audit log entry should be created"
            assert audit_log.success is True, "Audit log should mark success as True"
            if user:
                assert audit_log.user_id == user.id, f"Audit log should mark the SaaS account manager as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_6_3_list_accounts_with_pagination_parameters(self, authenticated_client, http_client):
        """Test Scenario 6.3: List Accounts with Pagination Parameters"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Test with page and page_size
        response1 = make_request(client, "get", "/accounts/?page=1&page_size=2")
        assert response1.status_code == 200
        data1 = response1.json()
        
        if isinstance(data1, dict) and "results" in data1:
            assert len(data1["results"]) <= 2, "Page size should be respected"

    def test_6_4_list_accounts_with_invalid_pagination_parameters(self, authenticated_client, http_client):
        """Test Scenario 6.4: List Accounts with Invalid Pagination Parameters"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Test invalid page numbers
        invalid_params = [
            ("?page_size=0", 400),
            ("?page_size=1000", 400),  # Exceeds maximum
            ("?page=-1", 404),
            ("?page=0", 404),
        ]
        
        for params, expected_status in invalid_params:
            response = make_request(client, "get", f"/accounts/{params}")
            assert response.status_code == expected_status or response.status_code == 200, \
                f"Expected {expected_status} or 200 for invalid params '{params}', got {response.status_code}"

    def test_6_5_list_accounts_with_filtering(self, authenticated_client, http_client):
        """Test Scenario 6.5: List Accounts with Filtering"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Test filtering by is_active
        response_active = make_request(client, "get", "/accounts/?is_active=true")
        assert response_active.status_code == 200
        
        response_inactive = make_request(client, "get", "/accounts/?is_active=false")
        assert response_inactive.status_code == 200

    def test_6_6_list_accounts_with_ordering(self, authenticated_client, http_client):
        """Test Scenario 6.6: List Accounts with Ordering"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Test ordering by name
        response_asc = make_request(client, "get", "/accounts/?ordering=name")
        assert response_asc.status_code == 200
        assert response_asc.json()["results"][0]["name"] == "Test Account Alpha"
        
        response_desc = make_request(client, "get", "/accounts/?ordering=-name")
        assert response_desc.status_code == 200
        assert response_desc.json()["results"][0]["name"] == "Test Account Gama"

    def test_6_7_list_accounts_by_unauthorized_user(self, authenticated_client, http_client):
        """Test Scenario 6.7: List Accounts by Unauthorized User"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        response = make_request(client, "get", "/accounts/")
        
        assert response.status_code == 403, \
            f"Expected 403 for unauthorized user, got {response.status_code}, response: {response.text}"

    def test_6_8_list_accounts_unauthenticated(self, http_client):
        """Test Scenario 6.8: List Accounts Unauthenticated"""
        response = make_request(http_client, "get", "/accounts/")
        
        assert response.status_code == 401, \
            f"Expected 401 for unauthenticated request, got {response.status_code}, response: {response.text}"


@pytest.mark.acceptance
class TestREQAccount007TransferAccountOwnership:
    """REQ-ACCOUNT-007: Transfer Account Ownership"""

    def test_7_1_transfer_ownership_by_account_owner(self, authenticated_client, http_client):
        """Test Scenario 7.1: Transfer Ownership by Account Owner"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get account owned by this user
        if DJANGO_AVAILABLE and Account:
            User = get_user_model()
            user = User.objects.using('default').filter(email=email).first()
            if user:
                account = Account.objects.using('default').filter(created_by=user).first()
                if account:
                    # Get another user to transfer to
                    target_user_email, _ = get_user_credentials("Account 1 Admin")
                    target_user = User.objects.using('default').filter(email=target_user_email).first()
                    
                    if target_user:
                        payload = {
                            "new_owner_user_id": target_user.id
                        }
                        response = make_request(client, "post", f"/accounts/{account.uuid}/transfer-owner/", json=payload)
                        
                        assert response.status_code == 200, \
                            f"Expected 200 but got {response.status_code}, response: {response.text}"
                        if DJANGO_AVAILABLE and AuditLog:
                            from django.utils import timezone
                            user = User.objects.using('default').filter(email=email).first()
                            audit_log = AuditLog.objects.using('default').filter(
                                path=f"/api/accounts/{account.uuid}/transfer-owner/",
                                method="POST",
                                status_code=200,
                                created_at__gte=timezone.now() - timedelta(seconds=5)
                            ).order_by("-created_at").first()
                            assert audit_log is not None, "Audit log entry should be created"
                            assert audit_log.success is True, "Audit log should mark success as True"
                            if user:
                                assert audit_log.user_id == user.id, f"Audit log should mark the account owner as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_7_2_transfer_ownership_by_saas_account_manager(self, authenticated_client, http_client):
        """Test Scenario 7.2: Transfer Ownership by SaaS Account Manager"""
        email, password = get_user_credentials("SaaS Account Manager")
        client = authenticated_client(email, password)
        
        # Get assigned account
        if DJANGO_AVAILABLE and Account:
            account = Account.objects.using('default').filter(name="Test Account Alpha").first()
            if account:
                User = get_user_model()
                target_user_email, _ = get_user_credentials("Account 1 Admin")
                target_user = User.objects.using('default').filter(email=target_user_email).first()
                
                if target_user:
                    payload = {
                        "new_owner_user_id": target_user.id
                    }
                    response = make_request(client, "post", f"/accounts/{account.uuid}/transfer-owner/", json=payload)
                    
                    # Should succeed if account is assigned
                    assert response.status_code in (200, 403), \
                        f"Expected 200 or 403, got {response.status_code}, response: {response.text}"

    def test_7_3_transfer_ownership_by_saas_admin(self, authenticated_client, http_client):
        """Test Scenario 7.3: Transfer Ownership by SaaS Administrator"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get any account
        if DJANGO_AVAILABLE and Account:
            account = Account.objects.using('default').filter(name="Test Account Alpha").first()
            if account:
                User = get_user_model()
                target_user_email, _ = get_user_credentials("Account 1 Admin")
                target_user = User.objects.using('default').filter(email=target_user_email).first()
                
                if target_user:
                    payload = {
                        "new_owner_user_id": target_user.id
                    }
                    response = make_request(client, "post", f"/accounts/{account.uuid}/transfer-owner/", json=payload)
                    
                    assert response.status_code == 200, \
                        f"Expected 200 but got {response.status_code}, response: {response.text}"

    def test_7_4_transfer_ownership_by_account_admin_unauthorized(self, authenticated_client, http_client):
        """Test Scenario 7.4: Transfer Ownership by Account Admin (Unauthorized)"""
        email, password = get_user_credentials("Account 1 Admin")
        client = authenticated_client(email, password)
        
        # Account Admin should not be able to transfer ownership
        if DJANGO_AVAILABLE and Account:
            account = Account.objects.using('default').filter(name="Test Account Alpha").first()
            if account:
                User = get_user_model()
                target_user_email, _ = get_user_credentials("Account 1 User 1")
                target_user = User.objects.using('default').filter(email=target_user_email).first()
                
                if target_user:
                    payload = {
                        "new_owner_user_id": target_user.id
                    }
                    response = make_request(client, "post", f"/accounts/{account.uuid}/transfer-owner/", json=payload)
                    
                    assert response.status_code == 403, \
                        f"Expected 403 for unauthorized transfer, got {response.status_code}, response: {response.text}"
                    data = response.json()
                    assert data.get("code") == "INSUFFICIENT_PERMISSIONS"
                    if DJANGO_AVAILABLE and AuditLog:
                        from django.utils import timezone
                        user = User.objects.using('default').filter(email=email).first()
                        audit_log = AuditLog.objects.using('default').filter(
                            path=f"/api/accounts/{account.uuid}/transfer-owner/",
                            method="POST",
                            status_code=403,
                            created_at__gte=timezone.now() - timedelta(seconds=5)
                        ).order_by("-created_at").first()
                        assert audit_log is not None, "Audit log entry should be created"
                        assert audit_log.success is False, "Audit log should mark success as False"
                        if user:
                            assert audit_log.user_id == user.id, f"Audit log should mark the account admin as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_7_5_transfer_ownership_to_invalid_user(self, authenticated_client, http_client):
        """Test Scenario 7.5: Transfer Ownership to Invalid User"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get account owned by this user
        if DJANGO_AVAILABLE and Account:
            User = get_user_model()
            user = User.objects.using('default').filter(email=email).first()
            if user:
                account = Account.objects.using('default').filter(created_by=user).first()
                if account:
                    # Use non-existent user ID
                    payload = {
                        "new_owner_user_id": 999999
                    }
                    response = make_request(client, "post", f"/accounts/{account.uuid}/transfer-owner/", json=payload)
                    
                    assert response.status_code == 400, \
                        f"Expected 400 for invalid user, got {response.status_code}, response: {response.text}"
                    data = response.json()
                    assert "code" in data or "user" in str(data).lower()
                    if DJANGO_AVAILABLE and AuditLog:
                        from django.utils import timezone
                        user = User.objects.using('default').filter(email=email).first()
                        audit_log = AuditLog.objects.using('default').filter(
                            path=f"/api/accounts/{account.uuid}/transfer-owner/",
                            method="POST",
                            status_code=400,
                            created_at__gte=timezone.now() - timedelta(seconds=5)
                        ).order_by("-created_at").first()
                        assert audit_log is not None, "Audit log entry should be created"
                        assert audit_log.success is False, "Audit log should mark success as False"
                        if user:
                            assert audit_log.user_id == user.id, f"Audit log should mark the account owner as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_7_6_transfer_ownership_of_nonexistent_account(self, authenticated_client, http_client):
        """Test Scenario 7.6: Transfer Ownership of Non-Existent Account"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        unowned_account = Account.objects.using('default').filter(name="Test Account Gamma").first()
        payload = {
            "new_owner_user_id": 1
        }
        response = make_request(client, "post", f"/accounts/{unowned_account.uuid}/transfer-owner/", json=payload)
        
        assert response.status_code in (404, 403), \
            f"Expected 404 or 403 for non-existent account, got {response.status_code}, response: {response.text}"

    def test_7_7_transfer_ownership_unauthenticated(self, http_client):
        """Test Scenario 7.7: Transfer Ownership Unauthenticated"""
        fake_uuid = str(uuid.uuid4())
        payload = {
            "new_owner_user_id": 1
        }
        response = make_request(http_client, "post", f"/accounts/{fake_uuid}/transfer-owner/", json=payload)
        
        assert response.status_code == 401, \
            f"Expected 401 for unauthenticated request, got {response.status_code}, response: {response.text}"


@pytest.mark.acceptance
class TestREQAccount008InputValidation:
    """REQ-ACCOUNT-008: Input Validation for Accounts"""

    def test_8_1_account_name_validation_allowed_characters(self, authenticated_client, http_client):
        """Test Scenario 8.1: Account Name Validation - Allowed Characters"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Test valid names with allowed characters (alphanumeric and spaces)
        valid_names = [
            "Test Account 123",
            "Test Account",
            "Test123",
            "Account Test",
            "Test Account Alpha Beta"
        ]
        
        for index, valid_name in enumerate(valid_names):
            payload = {
                "name": valid_name,
                "contact_email": f"test{int(time.time())}{index}@example.com"
            }
            response = make_request(client, "post", "/accounts/", json=payload)
            # Should succeed or fail for duplicate, but not for invalid characters
            assert response.status_code in (201, 409), \
                f"Valid name '{valid_name}' should be accepted, got {response.status_code}, response: {response.text}"

    def test_8_2_account_name_validation_invalid_characters(self, authenticated_client, http_client):
        """Test Scenario 8.2: Account Name Validation - Invalid Characters"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Test invalid names with disallowed characters (only alphanumeric and spaces allowed)
        invalid_names = [
            "Test@Account",  # @ not allowed
            "Test#Account",  # # not allowed
            "Test$Account",  # $ not allowed
            "Test%Account",  # % not allowed
            "Test&Account",  # & not allowed
            "Test*Account",  # * not allowed
            "Test(Account)",  # () not allowed
            "Test-Account",  # - not allowed
            "Test.Account",  # . not allowed
        ]
        
        for invalid_name in invalid_names:
            payload = {
                "name": invalid_name,
                "contact_email": f"test{int(time.time())}@example.com"
            }
            before_request = timezone.now() - timedelta(seconds=5)
            response = make_request(client, "post", "/accounts/", json=payload)
            
            assert response.status_code == 400, \
                f"Invalid name '{invalid_name}' should be rejected, got {response.status_code}, response: {response.text}"
            data = response.json()
            assert "name" in str(data).lower() or "invalid" in str(data).lower() or data.get("code") == "INVALID_ACCOUNT_DATA", \
                f"Response should indicate invalid name, got {data}"
            
            # Verify audit log
            if DJANGO_AVAILABLE and AuditLog:
                user = User.objects.using('default').filter(email=email).first()
                audit_log = AuditLog.objects.using('default').filter(
                    path="/api/accounts/",
                    method="POST",
                    status_code=400,
                    created_at__gte=before_request
                ).order_by("-created_at").first()
                if audit_log:
                    assert audit_log.success is False, "Audit log should mark success as False"
                    if user:
                        assert audit_log.user_id == user.id, \
                            f"Audit log should reference user: {audit_log.user_id} != {user.id}"

    def test_8_3_account_name_validation_length(self, authenticated_client, http_client):
        """Test Scenario 8.3: Account Name Validation - Length (1-100 chars)"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Test empty name
        payload1 = {
            "name": "",
            "contact_email": f"test{int(time.time())}@example.com"
        }
        response1 = make_request(client, "post", "/accounts/", json=payload1)
        assert response1.status_code == 400, \
            f"Expected 400 for empty name, got {response1.status_code}, response: {response1.text}"
        data1 = response1.json()
        assert "name" in str(data1).lower() or data1.get("code") == "INVALID_ACCOUNT_DATA", \
            f"Response should indicate invalid name, got {data1}"
        
        # Test name exceeding 100 characters
        long_name = "A" * 101
        payload2 = {
            "name": long_name,
            "contact_email": f"test{int(time.time())}@example.com"
        }
        response2 = make_request(client, "post", "/accounts/", json=payload2)
        assert response2.status_code == 400, \
            f"Expected 400 for name exceeding 100 chars, got {response2.status_code}, response: {response2.text}"
        data2 = response2.json()
        assert "name" in str(data2).lower() or "length" in str(data2).lower() or data2.get("code") == "INVALID_ACCOUNT_DATA", \
            f"Response should indicate invalid name length, got {data2}"

    def test_8_4_account_description_validation_allowed_characters(self, authenticated_client, http_client):
        """Test Scenario 8.4: Account Description Validation - Allowed Characters"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Test valid descriptions with allowed special characters
        # Allowed: alphanumeric, white spaces, new lines, and: ! * - ( ) # ? @ / ^ ~ . : ، ﷼ % & ' = + $ , [ ] ~
        valid_descriptions = [
            "Test description with allowed chars: ! * - ( ) # ? @ / ^ ~ . : ، ﷼ % & ' = + $ , [ ] ~",
            "Test description\nwith newlines",
            "Test description with spaces",
            "Test description with numbers 123",
        ]
        
        for index, valid_desc in enumerate(valid_descriptions):
            payload = {
                "name": f"Test Account {int(time.time())}{index}",
                "contact_email": f"test{int(time.time())}{index}@example.com",
                "description": valid_desc
            }
            response = make_request(client, "post", "/accounts/", json=payload)
            # Should succeed
            assert response.status_code == 201, \
                f"Valid description should be accepted, got {response.status_code}, response: {response.text}"

    def test_8_5_account_description_validation_length(self, authenticated_client, http_client):
        """Test Scenario 8.5: Account Description Validation - Length (max 500 chars)"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Test description exceeding 500 characters
        long_description = "A" * 501
        payload = {
            "name": f"Test Account {int(time.time())}",
            "contact_email": f"test{int(time.time())}@example.com",
            "description": long_description
        }
        response = make_request(client, "post", "/accounts/", json=payload)
        assert response.status_code == 400, \
            f"Expected 400 for description exceeding 500 chars, got {response.status_code}, response: {response.text}"
        data = response.json()
        assert "description" in str(data).lower() or "length" in str(data).lower() or data.get("code") == "INVALID_ACCOUNT_DATA", \
            f"Response should indicate invalid description length, got {data}"

    def test_8_6_account_contact_email_validation_allowed_characters(self, authenticated_client, http_client):
        """Test Scenario 8.6: Account Contact Email Validation - Allowed Characters"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Test valid emails with allowed characters
        # Allowed: English alphabets, numerical numbers, and: ! # $ % & ' * + - / = ? ^ _ { | } ~
        valid_emails = [
            f"test{int(time.time())}@example.com",
            f"test123{int(time.time())}@example.com",
            f"test+tag{int(time.time())}@example.com",
            f"test_name{int(time.time())}@example.com",
            f"test-name{int(time.time())}@example.com",
            f"test.name{int(time.time())}@example.com",
        ]
        
        for valid_email in valid_emails:
            payload = {
                "name": f"Test Account {int(time.time())}",
                "contact_email": valid_email
            }
            response = make_request(client, "post", "/accounts/", json=payload)
            # Should succeed or fail for duplicate, but not for invalid characters
            assert response.status_code in (201, 409), \
                f"Valid email '{valid_email}' should be accepted, got {response.status_code}, response: {response.text}"

    def test_8_7_account_contact_email_validation_invalid_characters(self, authenticated_client, http_client):
        """Test Scenario 8.7: Account Contact Email Validation - Invalid Characters"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Test invalid emails with disallowed characters
        # Not allowed in email: spaces, special chars not in allowed list, etc.
        invalid_emails = [
            "test with spaces@example.com",  # spaces not allowed
            "test@example.com with spaces",  # spaces not allowed
            "test(comment)@example.com",  # () not in allowed list for email
            "test[comment]@example.com",  # [] not in allowed list for email
        ]
        
        for invalid_email in invalid_emails:
            payload = {
                "name": f"Test Account {int(time.time())}",
                "contact_email": invalid_email
            }
            before_request = timezone.now() - timedelta(seconds=5)
            response = make_request(client, "post", "/accounts/", json=payload)
            
            assert response.status_code == 400, \
                f"Invalid email '{invalid_email}' should be rejected, got {response.status_code}, response: {response.text}"
            data = response.json()
            assert "email" in str(data).lower() or "contact_email" in str(data).lower() or data.get("code") == "INVALID_ACCOUNT_DATA", \
                f"Response should indicate invalid email, got {data}"
            
            # Verify audit log
            if DJANGO_AVAILABLE and AuditLog:
                user = User.objects.using('default').filter(email=email).first()
                audit_log = AuditLog.objects.using('default').filter(
                    path="/api/accounts/",
                    method="POST",
                    status_code=400,
                    created_at__gte=before_request
                ).order_by("-created_at").first()
                if audit_log:
                    assert audit_log.success is False, "Audit log should mark success as False"
                    if user:
                        assert audit_log.user_id == user.id, \
                            f"Audit log should reference user: {audit_log.user_id} != {user.id}"

    def test_8_8_account_contact_email_validation_format(self, authenticated_client, http_client):
        """Test Scenario 8.8: Account Contact Email Validation - Format"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Test invalid email formats
        invalid_formats = [
            "notanemail",
            "missing@domain",
            "@nodomain.com",
            "nodomain@",
            "test@",
            "@test.com",
        ]
        
        for invalid_format in invalid_formats:
            payload = {
                "name": f"Test Account {int(time.time())}",
                "contact_email": invalid_format
            }
            response = make_request(client, "post", "/accounts/", json=payload)
            assert response.status_code == 400, \
                f"Invalid email format '{invalid_format}' should be rejected, got {response.status_code}, response: {response.text}"
            data = response.json()
            assert "email" in str(data).lower() or "contact_email" in str(data).lower() or data.get("code") == "INVALID_ACCOUNT_DATA", \
                f"Response should indicate invalid email format, got {data}"