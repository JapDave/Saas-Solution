"""
Acceptance tests for Organization Management API endpoints.

These tests verify the actual HTTP API behavior end-to-end,
including authentication, authorization, and response formats.

Tests are organized by requirement (REQ-ORG-XXX) from:
- ORGANIZATION-MANAGEMENT.md
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
    from apps.organizations.models import Organization
    from apps.users.models import User, UserOrganization
    from apps.common.models import AuditLog, DataChangeLog
    from apps.subscriptions.models import Subscription
    DJANGO_AVAILABLE = True
except ImportError:
    DJANGO_AVAILABLE = False
    User = None
    Account = None
    Organization = None
    UserOrganization = None
    AuditLog = None
    DataChangeLog = None
    Subscription = None
    get_user_model = None
    connection = None
    connections = None
    settings = None
    timezone = None


@pytest.mark.acceptance
class TestREQOrg001CreateOrganization:
    """REQ-ORG-001: Create Organization"""

    def test_1_1_create_organization_with_owner_by_account_owner(self, authenticated_client, http_client):
        """Test Scenario 1.1: Happy Path with Owner"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get account for this user
        if DJANGO_AVAILABLE and Account and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                account = Account.objects.using('default').filter(created_by=user).first()
                if account:
                    # Get a member user to assign as owner
                    owner_email, _ = get_user_credentials("Account 1 User 1")
                    owner_user = User.objects.using('default').filter(email=owner_email).first()
                    
                    if owner_user:
                        payload = {
                            "account": account.id,
                            "name": f"New Organization {int(time.time())}",
                            "description": "Test organization with owner",
                            "owner": owner_user.id
                        }
                        
                        start_time = time.time()
                        response = make_request(client, "post", "/organizations/", json=payload)
                        response_time = time.time() - start_time
                        
                        assert response.status_code == 201, \
                            f"Expected 201 but got {response.status_code}, response: {response.text}"
                        data = response.json()
                        
                        assert data.get("name") == payload["name"], "Organization name should match"
                        assert data.get("account") == account.id, "Account ID should match"
                        assert response_time < 2.0, f"Response time should be less than 2 seconds, got {response_time:.2f}s"
                        
                        # Verify audit log
                        if DJANGO_AVAILABLE and AuditLog:
                            before_request = timezone.now() - timedelta(seconds=5)
                            audit_user = User.objects.using('default').filter(email=email).first()
                            org_uuid = data.get("uuid") or data.get("id")
                            
                            audit_log = AuditLog.objects.using('default').filter(
                                path="/api/organizations/",
                                method="POST",
                                status_code=201,
                                created_at__gte=before_request
                            ).order_by("-created_at").first()
                            assert audit_log is not None, "Audit log entry should be created"
                            assert audit_log.success is True, "Audit log should mark success as True"
                            if audit_user:
                                assert audit_log.user_id == audit_user.id, \
                                    f"Audit log should reference the correct user: {audit_log.user_id} != {audit_user.id}"
                            
                            # Verify DataChangeLog for CREATE operation
                            if DataChangeLog and org_uuid:
                                data_change_log = DataChangeLog.objects.using('default').filter(
                                    app_label="organizations",
                                    model_name="Organization",
                                    action="create",
                                    object_id=str(org_uuid),
                                    created_at__gte=before_request
                                ).order_by("-created_at").first()
                                
                                assert data_change_log is not None, "DataChangeLog entry should be created for CREATE"
                                assert data_change_log.audit_log_id == audit_log.id, \
                                    f"DataChangeLog audit_log_id should match AuditLog id: {data_change_log.audit_log_id} != {audit_log.id}"
                                assert data_change_log.user_id == audit_user.id, \
                                    f"DataChangeLog user_id should match user: {data_change_log.user_id} != {audit_user.id}"
                                assert data_change_log.trace_id is not None, "DataChangeLog trace_id should not be null"
                                assert data_change_log.span_id is not None, "DataChangeLog span_id should not be null"
                                
                                # Verify changed_fields contains expected fields
                                changed_fields = data_change_log.changed_fields
                                assert isinstance(changed_fields, dict), "changed_fields should be a dictionary"
                                assert "name" in changed_fields, "changed_fields should contain 'name'"
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

    def test_1_2_create_organization_auto_owner_by_account_owner(self, authenticated_client, http_client):
        """Test Scenario 1.2: Happy Path Auto-Owner"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get account for this user
        if DJANGO_AVAILABLE and Account and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                account = Account.objects.using('default').filter(created_by=user).first()
                if account:
                    payload = {
                        "account": account.id,
                        "name": f"Auto Owner Org {int(time.time())}",
                        "description": "Test organization without owner specified"
                    }
                    
                    response = make_request(client, "post", "/organizations/", json=payload)
                    
                    assert response.status_code == 201, \
                        f"Expected 201 but got {response.status_code}, response: {response.text}"
                    data = response.json()
                    assert data.get("name") == payload["name"], "Organization name should match"
                    # Creator should become owner automatically
                    if DJANGO_AVAILABLE and AuditLog:
                        audit_user = User.objects.using('default').filter(email=email).first()
                        audit_log = AuditLog.objects.using('default').filter(
                            path="/api/organizations/",
                            method="POST",
                            status_code=201,
                            created_at__gte=timezone.now() - timedelta(seconds=5)
                        ).order_by("-created_at").first()
                        assert audit_log is not None, "Audit log entry should be created"
                        assert audit_log.success is True, "Audit log should mark success as True"
                        if audit_user:
                            assert audit_log.user_id == audit_user.id, \
                                f"Audit log should reference the correct user: {audit_log.user_id} != {audit_user.id}"

    def test_1_3_create_organization_saas_admin_error_no_owner(self, authenticated_client, http_client):
        """Test Scenario 1.3: SaaS Admin Error - No Owner"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get any account
        if DJANGO_AVAILABLE and Account:
            account = Account.objects.using('default').filter(name="Test Account Alpha").first()
            if account:
                payload = {
                    "account": account.id,
                    "name": f"SaaS Admin Test {int(time.time())}"
                }
                
                response = make_request(client, "post", "/organizations/", json=payload)
                
                assert response.status_code == 400, \
                    f"Expected 400 for SaaS Admin without owner, got {response.status_code}, response: {response.text}"
                data = response.json()
                assert "owner" in str(data).lower() or "code" in data, \
                    f"Response should indicate owner is required, got {data}"
                if DJANGO_AVAILABLE and AuditLog:
                    user = User.objects.using('default').filter(email=email).first()
                    audit_log = AuditLog.objects.using('default').filter(
                        path="/api/organizations/",
                        method="POST",
                        status_code=400,
                        created_at__gte=timezone.now() - timedelta(seconds=5)
                    ).order_by("-created_at").first()
                    assert audit_log is not None, "Audit log entry should be created"
                    assert audit_log.success is False, "Audit log should mark success as False"
                    if user:
                        assert audit_log.user_id == user.id, f"Audit log should mark the super admin as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_1_4_create_organization_saas_account_manager_error_no_owner(self, authenticated_client, http_client):
        """Test Scenario 1.4: SaaS Account Manager Error - No Owner"""
        email, password = get_user_credentials("SaaS Account Manager")
        client = authenticated_client(email, password)
        
        # Get assigned account
        if DJANGO_AVAILABLE and Account:
            account = Account.objects.using('default').filter(name="Test Account Alpha").first()
            if account:
                payload = {
                    "account": account.id,
                    "name": f"Manager Test {int(time.time())}"
                }
                
                response = make_request(client, "post", "/organizations/", json=payload)
                
                assert response.status_code == 400, \
                    f"Expected 400 for SaaS Account Manager without owner, got {response.status_code}, response: {response.text}"
                data = response.json()
                assert "owner" in str(data).lower() or "code" in data, \
                    f"Response should indicate owner is required, got {data}"
                if DJANGO_AVAILABLE and AuditLog:
                    user = User.objects.using('default').filter(email=email).first()
                    audit_log = AuditLog.objects.using('default').filter(
                        path="/api/organizations/",
                        method="POST",
                        status_code=400,
                        created_at__gte=timezone.now() - timedelta(seconds=5)
                    ).order_by("-created_at").first()
                    assert audit_log is not None, "Audit log entry should be created"
                    assert audit_log.success is False, "Audit log should mark success as False"
                    if user:
                        assert audit_log.user_id == user.id, f"Audit log should mark the SaaS Account Manager as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_1_5_create_organization_unauthorized_different_account(self, authenticated_client, http_client):
        """Test Scenario 1.5: Unauthorized - Different Account"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Try to create organization in Account 2
        if DJANGO_AVAILABLE and Account:
            account = Account.objects.using('default').filter(name="Test Account Beta").first()
            if account:
                payload = {
                    "account": account.id,
                    "name": f"Unauthorized Test {int(time.time())}"
                }
                
                response = make_request(client, "post", "/organizations/", json=payload)
                
                assert response.status_code == 403, \
                    f"Expected 403 for unauthorized account, got {response.status_code}, response: {response.text}"
                data = response.json()
                assert data.get("code") == "INSUFFICIENT_PERMISSIONS" or "permission" in str(data).lower(), \
                    f"Response should indicate insufficient permissions, got {data}"
                assert data.get("code") == "INSUFFICIENT_PERMISSIONS"
                if DJANGO_AVAILABLE and AuditLog:
                    user = User.objects.using('default').filter(email=email).first()
                    audit_log = AuditLog.objects.using('default').filter(
                        path="/api/organizations/",
                        method="POST",
                        status_code=403,
                        created_at__gte=timezone.now() - timedelta(seconds=5)
                    ).order_by("-created_at").first()
                    assert audit_log is not None, "Audit log entry should be created"
                    assert audit_log.success is False, "Audit log should mark success as False"
                    if user:
                        assert audit_log.user_id == user.id, f"Audit log should mark the account owner as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_1_6_create_organization_duplicate_name(self, authenticated_client, http_client):
        """Test Scenario 1.6: Duplicate Name"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get account for this user
        if DJANGO_AVAILABLE and Account and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                account = Account.objects.using('default').filter(created_by=user).first()
                if account:
                    # Create first organization
                    timestamp = int(time.time())
                    payload1 = {
                        "account": account.id,
                        "name": f"Duplicate Test Org {timestamp}"
                    }
                    response1 = make_request(client, "post", "/organizations/", json=payload1)
                    assert response1.status_code == 201
                    
                    # Try to create another with same name
                    payload2 = {
                        "account": account.id,
                        "name": payload1["name"]  # Same name
                    }
                    response2 = make_request(client, "post", "/organizations/", json=payload2)
                    
                    assert response2.status_code == 400, \
                        f"Expected 400 for duplicate name, got {response2.status_code}, response: {response2.text}"
                    data = response2.json()
                    assert data.get("code") == "ORGANIZATION_NAME_EXISTS" or "name" in str(data).lower(), \
                        f"Response should indicate duplicate name, got {data}"
                    assert data.get("code") == "ORGANIZATION_NAME_EXISTS"
                    if DJANGO_AVAILABLE and AuditLog:
                        user = User.objects.using('default').filter(email=email).first()
                        audit_log = AuditLog.objects.using('default').filter(
                            path="/api/organizations/",
                            method="POST",
                            status_code=400,
                            created_at__gte=timezone.now() - timedelta(seconds=5)
                        ).order_by("-created_at").first()
                        assert audit_log is not None, "Audit log entry should be created"
                        assert audit_log.success is False, "Audit log should mark success as False"
                        if user:
                            assert audit_log.user_id == user.id, f"Audit log should mark the account owner as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_1_7_create_organization_invalid_owner_non_member(self, authenticated_client, http_client):
        """Test Scenario 1.7: Invalid Owner - Non-Member"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get account for this user
        if DJANGO_AVAILABLE and Account and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                account = Account.objects.using('default').filter(created_by=user).first()
                if account:
                    # Get a user from a different account
                    other_account_user_email, _ = get_user_credentials("Account 2 Owner")
                    other_user = User.objects.using('default').filter(email=other_account_user_email).first()
                    
                    if other_user:
                        payload = {
                            "account": account.id,
                            "name": f"Invalid Owner Test {int(time.time())}",
                            "owner": other_user.id
                        }
                        
                        response = make_request(client, "post", "/organizations/", json=payload)
                        
                        assert response.status_code == 400, \
                            f"Expected 400 for non-member owner, got {response.status_code}, response: {response.text}"
                        data = response.json()
                        assert "member" in str(data).lower() or "code" in data, \
                            f"Response should indicate user is not a member, got {data}"
                        assert data.get("code") == "USER_NOT_ORGANIZATION_MEMBER" or "member" in str(data).lower()
                        if DJANGO_AVAILABLE and AuditLog:
                            user = User.objects.using('default').filter(email=email).first()
                            audit_log = AuditLog.objects.using('default').filter(
                                path="/api/organizations/",
                                method="POST",
                                status_code=400,
                                created_at__gte=timezone.now() - timedelta(seconds=5)
                            ).order_by("-created_at").first()
                            assert audit_log is not None, "Audit log entry should be created"
                            assert audit_log.success is False, "Audit log should mark success as False"
                            if user:
                                assert audit_log.user_id == user.id, f"Audit log should mark the account owner as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_1_8_create_organization_invalid_data(self, authenticated_client, http_client):
        """Test Scenario 1.8: Invalid Data"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get account for this user
        if DJANGO_AVAILABLE and Account and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                account = Account.objects.using('default').filter(created_by=user).first()
                if account:
                    # Test missing required fields
                    payload1 = {
                        "name": f"Test {int(time.time())}"
                        # Missing account
                    }
                    response1 = make_request(client, "post", "/organizations/", json=payload1)
                    assert response1.status_code == 400, \
                        f"Expected 400 for missing account, got {response1.status_code}, response: {response1.text}"
                    data1 = response1.json()
                    assert data1.get("code") == "INVALID_ORGANIZATION_DATA"
                    
                    # Test invalid logo URL
                    payload2 = {
                        "account": account.id,
                        "name": f"Invalid URL Test {int(time.time())}",
                        "logo_url": "not-a-valid-url"
                    }
                    response2 = make_request(client, "post", "/organizations/", json=payload2)
                    assert response2.status_code == 400, \
                        f"Expected 400 for invalid logo URL, got {response2.status_code}, response: {response2.text}"
                    data2 = response2.json()
                    assert data2.get("code") == "INVALID_LOGO_URL" or "logo" in str(data2).lower()
                    if DJANGO_AVAILABLE and AuditLog:
                        user = User.objects.using('default').filter(email=email).first()
                        audit_log = AuditLog.objects.using('default').filter(
                            path="/api/organizations/",
                            method="POST",
                            status_code=400,
                            created_at__gte=timezone.now() - timedelta(seconds=5)
                        ).order_by("-created_at").first()
                        assert audit_log is not None, "Audit log entry should be created"
                        assert audit_log.success is False, "Audit log should mark success as False"
                        if user:
                            assert audit_log.user_id == user.id, f"Audit log should mark the account owner as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_1_9_create_organization_unauthenticated(self, http_client):
        """Test Scenario 1.9: Create Organization Unauthenticated"""
        payload = {
            "account": 1,
            "name": "Test Organization"
        }
        response = make_request(http_client, "post", "/organizations/", json=payload)
        
        assert response.status_code == 401, \
            f"Expected 401 for unauthenticated request, got {response.status_code}, response: {response.text}"

    def test_1_10_org_admin_cannot_access_alpha2_organization(self, authenticated_client, http_client):
        """Test Scenario 1.10: Org Admin Cannot Access Test Organization Alpha2"""
        email, password = get_user_credentials("Account 1 Org Admin")
        client = authenticated_client(email, password)
        
        # Account 1 Org Admin should not have access to Test Organization Alpha2
        if DJANGO_AVAILABLE and Organization and Account:
            account = Account.objects.using('default').filter(name="Test Account Alpha").first()
            if account:
                org = Organization.objects.using('default').filter(
                    account=account,
                    name="Test Organization Alpha2"
                ).first()
                if org:
                    payload = {
                        "account": account.id,
                        "name": f"Test Org {int(time.time())}",
                        "description": "Test"
                    }
                    before_request = timezone.now() - timedelta(seconds=5)
                    response = make_request(client, "post", "/organizations/", json=payload)
                    
                    # Org Admin should not be able to create organizations (only Account Owner/Admin can)
                    # But if they try to access Alpha2, they should get 403
                    assert response.status_code in (403, 400), \
                        f"Expected 403 or 400 for org admin creating org, got {response.status_code}, response: {response.text}"
                    
                    # Verify audit log
                    if DJANGO_AVAILABLE and AuditLog:
                        user = User.objects.using('default').filter(email=email).first()
                        audit_log = AuditLog.objects.using('default').filter(
                            path="/api/organizations/",
                            method="POST",
                            status_code__in=[403, 400],
                            created_at__gte=before_request
                        ).order_by("-created_at").first()
                        if audit_log:
                            assert audit_log.success is False, "Audit log should mark success as False"
                            if user:
                                assert audit_log.user_id == user.id, \
                                    f"Audit log should reference user: {audit_log.user_id} != {user.id}"


@pytest.mark.acceptance
class TestREQOrg002RetrieveOrganizationInformation:
    """REQ-ORG-002: Retrieve Organization Information"""

    def test_2_1_retrieve_organization_by_org_owner(self, authenticated_client, http_client):
        """Test Scenario 2.1: Org Owner"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get organization owned by this user
        if DJANGO_AVAILABLE and Organization and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                # Find organization where user is owner
                from apps.roles.models import RoleAssignment
                from apps.roles.constants import ROLE_ORGANIZATION_OWNER
                
                org_assignments = RoleAssignment.objects.using('default').filter(
                    user=user,
                    role__key=ROLE_ORGANIZATION_OWNER,
                    deleted_at__isnull=True
                ).first()
                
                if org_assignments and org_assignments.organization:
                    org = org_assignments.organization
                    response = make_request(client, "get", f"/organizations/{org.uuid}/")
                    
                    assert response.status_code == 200, \
                        f"Expected 200 but got {response.status_code}, response: {response.text}"
                    data = response.json()
                    assert data.get("uuid") == str(org.uuid) or data.get("id") == org.id, \
                        "Organization UUID should match"
                    if DJANGO_AVAILABLE and AuditLog:
                        user = User.objects.using('default').filter(email=email).first()
                        audit_log = AuditLog.objects.using('default').filter(
                            path=f"/api/organizations/{org.uuid}/",
                            method="GET",
                            status_code=200,
                            created_at__gte=timezone.now() - timedelta(seconds=5)
                        ).order_by("-created_at").first()
                        assert audit_log is not None, "Audit log entry should be created"
                        assert audit_log.success is True, "Audit log should mark success as True"
                        if user:
                            assert audit_log.user_id == user.id, f"Audit log should mark the organization owner as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_2_2_retrieve_organization_by_org_admin(self, authenticated_client, http_client):
        """Test Scenario 2.2: Org Admin"""
        email, password = get_user_credentials("Account 1 Org Admin")
        client = authenticated_client(email, password)
        
        # Get organization for this user
        if DJANGO_AVAILABLE and Organization and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                user_org = UserOrganization.objects.using('default').filter(user=user).first()
                if user_org and user_org.organization:
                    org = user_org.organization
                    response = make_request(client, "get", f"/organizations/{org.uuid}/")
                    
                    assert response.status_code == 200, \
                        f"Expected 200 but got {response.status_code}, response: {response.text}"

    def test_2_3_retrieve_organization_by_org_member(self, authenticated_client, http_client):
        """Test Scenario 2.3: Org Member"""
        email, password = get_user_credentials("Account 1 User 1")
        client = authenticated_client(email, password)
        
        # Get organization for this user
        if DJANGO_AVAILABLE and Organization and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                user_org = UserOrganization.objects.using('default').filter(user=user).first()
                if user_org and user_org.organization:
                    org = user_org.organization
                    response = make_request(client, "get", f"/organizations/{org.uuid}/")
                    
                    assert response.status_code == 200, \
                        f"Expected 200 but got {response.status_code}, response: {response.text}"

    def test_2_4_retrieve_organization_by_account_owner(self, authenticated_client, http_client):
        """Test Scenario 2.4: Account Owner"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get organization in account owned by this user
        if DJANGO_AVAILABLE and Organization and Account and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                account = Account.objects.using('default').filter(created_by=user).first()
                if account:
                    org = Organization.objects.using('default').filter(account=account).first()
                    if org:
                        response = make_request(client, "get", f"/organizations/{org.uuid}/")
                        
                        assert response.status_code == 200, \
                            f"Expected 200 but got {response.status_code}, response: {response.text}"

    def test_2_5_retrieve_organization_by_saas_account_manager(self, authenticated_client, http_client):
        """Test Scenario 2.5: SaaS Account Manager"""
        email, password = get_user_credentials("SaaS Account Manager")
        client = authenticated_client(email, password)
        
        # Get organization in assigned account
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if org:
                response = make_request(client, "get", f"/organizations/{org.uuid}/")
                
                assert response.status_code == 200, \
                    f"Expected 200 but got {response.status_code}, response: {response.text}"

    def test_2_6_retrieve_organization_unauthorized_different_account(self, authenticated_client, http_client):
        """Test Scenario 2.6: Unauthorized - Different Account"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Try to access organization in Account 2
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Beta1").first()
            if org:
                response = make_request(client, "get", f"/organizations/{org.uuid}/")
                
                assert response.status_code == 403, \
                    f"Expected 403 for unauthorized access, got {response.status_code}, response: {response.text}"
                data = response.json()
                assert data.get("code") == "INSUFFICIENT_PERMISSIONS" or "permission" in str(data).lower(), \
                    f"Response should indicate insufficient permissions, got {data}"
                assert data.get("code") == "INSUFFICIENT_PERMISSIONS"
                if DJANGO_AVAILABLE and AuditLog:
                    user = User.objects.using('default').filter(email=email).first()
                    audit_log = AuditLog.objects.using('default').filter(
                        path=f"/api/organizations/{org.uuid}/",
                        method="GET",
                        status_code=403,
                        created_at__gte=timezone.now() - timedelta(seconds=5)
                    ).order_by("-created_at").first()
                    assert audit_log is not None, "Audit log entry should be created"
                    assert audit_log.success is False, "Audit log should mark success as False"
                    if user:
                        assert audit_log.user_id == user.id, f"Audit log should mark the account owner as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_2_7_retrieve_nonexistent_organization(self, authenticated_client, http_client):
        """Test Scenario 2.7: Retrieve Non-Existent Organization"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        fake_uuid = str(uuid.uuid4())
        response = make_request(client, "get", f"/organizations/{fake_uuid}/")
        
        assert response.status_code == 404, \
            f"Expected 404 for non-existent organization, got {response.status_code}, response: {response.text}"
        data = response.json()
        assert "code" in data or "not found" in str(data).lower(), \
            f"Response should indicate organization not found, got {data}"
        assert data.get("code") == "ORGANIZATION_NOT_FOUND"
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path__startswith="/api/organizations/",
                method="GET",
                status_code=404,
                created_at__gte=timezone.now() - timedelta(seconds=5)
            ).order_by("-created_at").first()
            assert audit_log is not None, "Audit log entry should be created"
            assert audit_log.success is False, "Audit log should mark success as False"
            if user:
                assert audit_log.user_id == user.id, f"Audit log should mark the super admin as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_2_8_retrieve_organization_unauthenticated(self, http_client):
        """Test Scenario 2.8: Retrieve Organization Unauthenticated"""
        fake_uuid = str(uuid.uuid4())
        response = make_request(http_client, "get", f"/organizations/{fake_uuid}/")
        
        assert response.status_code == 401, \
            f"Expected 401 for unauthenticated request, got {response.status_code}, response: {response.text}"

    def test_2_9_org_admin_cannot_retrieve_alpha2_organization(self, authenticated_client, http_client):
        """Test Scenario 2.9: Org Admin Cannot Retrieve Test Organization Alpha2"""
        email, password = get_user_credentials("Account 1 Org Admin")
        client = authenticated_client(email, password)
        
        # Account 1 Org Admin should not have access to Test Organization Alpha2
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha2").first()
            if org:
                before_request = timezone.now() - timedelta(seconds=5)
                response = make_request(client, "get", f"/organizations/{org.uuid}/")
                
                assert response.status_code == 403, \
                    f"Expected 403 for org admin accessing Alpha2, got {response.status_code}, response: {response.text}"
                data = response.json()
                assert data.get("code") == "INSUFFICIENT_PERMISSIONS", \
                    f"Response should indicate insufficient permissions, got {data}"
                
                # Verify audit log
                if DJANGO_AVAILABLE and AuditLog:
                    user = User.objects.using('default').filter(email=email).first()
                    audit_log = AuditLog.objects.using('default').filter(
                        path=f"/api/organizations/{org.uuid}/",
                        method="GET",
                        status_code=403,
                        created_at__gte=before_request
                    ).order_by("-created_at").first()
                    assert audit_log is not None, "Audit log entry should be created"
                    assert audit_log.success is False, "Audit log should mark success as False"
                    if user:
                        assert audit_log.user_id == user.id, \
                            f"Audit log should reference user: {audit_log.user_id} != {user.id}"


@pytest.mark.acceptance
class TestREQOrg003UpdateOrganizationInformation:
    """REQ-ORG-003: Update Organization Information"""

    def test_3_1_update_organization_by_org_owner(self, authenticated_client, http_client):
        """Test Scenario 3.1: Happy Path"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get organization owned by this user
        if DJANGO_AVAILABLE and Organization and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                from apps.roles.models import RoleAssignment
                from apps.roles.constants import ROLE_ORGANIZATION_OWNER
                
                org_assignment = RoleAssignment.objects.using('default').filter(
                    user=user,
                    role__key=ROLE_ORGANIZATION_OWNER,
                    deleted_at__isnull=True
                ).first()
                
                if org_assignment and org_assignment.organization:
                    org = org_assignment.organization
                    payload = {
                        "account": org.account.id,
                        "name": f"Updated Org Name {int(time.time())}",
                        "description": "Updated description"
                    }
                    
                    response = make_request(client, "put", f"/organizations/{org.uuid}/", json=payload)
                    
                    assert response.status_code == 200, \
                        f"Expected 200 but got {response.status_code}, response: {response.text}"
                    data = response.json()
                    assert data.get("name") == payload["name"], "Organization name should be updated"
                    if DJANGO_AVAILABLE and AuditLog:
                        user = User.objects.using('default').filter(email=email).first()
                        audit_log = AuditLog.objects.using('default').filter(
                            path=f"/api/organizations/{org.uuid}/",
                            method="PUT",
                            status_code=200,
                            created_at__gte=timezone.now() - timedelta(seconds=5)
                        ).order_by("-created_at").first()
                        assert audit_log is not None, "Audit log entry should be created"
                        assert audit_log.success is True, "Audit log should mark success as True"
                        if user:
                            assert audit_log.user_id == user.id, f"Audit log should mark the organization owner as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_3_2_update_organization_by_org_admin(self, authenticated_client, http_client):
        """Test Scenario 3.2: Org Admin"""
        email, password = get_user_credentials("Account 1 Org Admin")
        client = authenticated_client(email, password)
        
        # Get organization for this user
        if DJANGO_AVAILABLE and Organization and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                user_org = UserOrganization.objects.using('default').filter(user=user).first()
                if user_org and user_org.organization:
                    org = user_org.organization
                    payload = {
                        "account": org.account.id,
                        "name": org.name,
                        "description": f"Updated by admin {int(time.time())}"
                    }
                    
                    response = make_request(client, "put", f"/organizations/{org.uuid}/", json=payload)
                    
                    assert response.status_code == 200, \
                        f"Expected 200 but got {response.status_code}, response: {response.text}"

    def test_3_3_update_organization_by_account_admin(self, authenticated_client, http_client):
        """Test Scenario 3.3: Account Admin"""
        email, password = get_user_credentials("Account 1 Admin")
        client = authenticated_client(email, password)
        
        # Get organization in account
        if DJANGO_AVAILABLE and Organization and Account and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                user_org = UserOrganization.objects.using('default').filter(user=user).first()
                if user_org and user_org.organization:
                    account = user_org.organization.account
                    org = Organization.objects.using('default').filter(account=account).first()
                    if org:
                        payload = {
                            "account": org.account.id,
                            "name": org.name,
                            "description": f"Updated by account admin {int(time.time())}"
                        }
                        
                        response = make_request(client, "put", f"/organizations/{org.uuid}/", json=payload)
                        
                        assert response.status_code == 200, \
                            f"Expected 200 but got {response.status_code}, response: {response.text}"

    def test_3_4_update_organization_by_saas_account_manager(self, authenticated_client, http_client):
        """Test Scenario 3.4: SaaS Account Manager"""
        email, password = get_user_credentials("SaaS Account Manager")
        client = authenticated_client(email, password)
        
        # Get organization in assigned account
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if org:
                payload = {
                    "account": org.account.id,
                    "name": org.name,
                    "description": f"Updated by manager {int(time.time())}"
                }
                
                response = make_request(client, "put", f"/organizations/{org.uuid}/", json=payload)
                
                assert response.status_code == 200, \
                    f"Expected 200 but got {response.status_code}, response: {response.text}"

    def test_3_5_update_organization_unauthorized_different_org(self, authenticated_client, http_client):
        """Test Scenario 3.5: Unauthorized - Different Organization"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Try to update organization in Account 2
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Beta1").first()
            if org:
                payload = {
                    "account": org.account.id,
                    "name": org.name,
                    "description": "Unauthorized update"
                }
                
                response = make_request(client, "put", f"/organizations/{org.uuid}/", json=payload)
                
                assert response.status_code == 403, \
                    f"Expected 403 for unauthorized update, got {response.status_code}, response: {response.text}"
                data = response.json()
                assert data.get("code") == "INSUFFICIENT_PERMISSIONS"
                if DJANGO_AVAILABLE and AuditLog:
                    user = User.objects.using('default').filter(email=email).first()
                    audit_log = AuditLog.objects.using('default').filter(
                        path=f"/api/organizations/{org.uuid}/",
                        method="PUT",
                        status_code=403,
                        created_at__gte=timezone.now() - timedelta(seconds=5)
                    ).order_by("-created_at").first()
                    assert audit_log is not None, "Audit log entry should be created"
                    assert audit_log.success is False, "Audit log should mark success as False"
                    if user:
                        assert audit_log.user_id == user.id, f"Audit log should mark the account owner as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_3_6_update_organization_url_validation(self, authenticated_client, http_client):
        """Test Scenario 3.6: URL Validation"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get organization owned by this user
        if DJANGO_AVAILABLE and Organization and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                from apps.roles.models import RoleAssignment
                from apps.roles.constants import ROLE_ORGANIZATION_OWNER
                
                org_assignment = RoleAssignment.objects.using('default').filter(
                    user=user,
                    role__key=ROLE_ORGANIZATION_OWNER,
                    deleted_at__isnull=True
                ).first()
                
                if org_assignment and org_assignment.organization:
                    org = org_assignment.organization
                    payload = {
                        "account": org.account.id,
                        "name": org.name,
                        "logo_url": "invalid-url-format"
                    }
                    
                    response = make_request(client, "put", f"/organizations/{org.uuid}/", json=payload)
                    
                    assert response.status_code == 400, \
                        f"Expected 400 for invalid logo URL, got {response.status_code}, response: {response.text}"
                    data = response.json()
                    assert data.get("code") == "INVALID_LOGO_URL" or "logo" in str(data).lower()
                    if DJANGO_AVAILABLE and AuditLog:
                        user = User.objects.using('default').filter(email=email).first()
                        audit_log = AuditLog.objects.using('default').filter(
                            path=f"/api/organizations/{org.uuid}/",
                            method="PUT",
                            status_code=400,
                            created_at__gte=timezone.now() - timedelta(seconds=5)
                        ).order_by("-created_at").first()
                        assert audit_log is not None, "Audit log entry should be created"
                        assert audit_log.success is False, "Audit log should mark success as False"
                        if user:
                            assert audit_log.user_id == user.id, f"Audit log should mark the organization owner as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_3_7_partial_update_organization(self, authenticated_client, http_client):
        """Test Scenario 3.7: Partial Update with PATCH"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get organization owned by this user
        if DJANGO_AVAILABLE and Organization and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                from apps.roles.models import RoleAssignment
                from apps.roles.constants import ROLE_ORGANIZATION_OWNER
                
                org_assignment = RoleAssignment.objects.using('default').filter(
                    user=user,
                    role__key=ROLE_ORGANIZATION_OWNER,
                    deleted_at__isnull=True
                ).first()
                
                if org_assignment and org_assignment.organization:
                    org = org_assignment.organization
                    # Use PATCH for partial update
                    payload = {
                        "description": f"Partially updated {int(time.time())}"
                    }
                    
                    response = make_request(client, "patch", f"/organizations/{org.uuid}/", json=payload)
                    
                    assert response.status_code == 200, \
                        f"Expected 200 but got {response.status_code}, response: {response.text}"
                    data = response.json()
                    assert data.get("description") == payload["description"], "Description should be updated"
                    if DJANGO_AVAILABLE and AuditLog:
                        user = User.objects.using('default').filter(email=email).first()
                        audit_log = AuditLog.objects.using('default').filter(
                            path=f"/api/organizations/{org.uuid}/",
                            method="PATCH",
                            status_code=200,
                            created_at__gte=timezone.now() - timedelta(seconds=5)
                        ).order_by("-created_at").first()
                        assert audit_log is not None, "Audit log entry should be created"
                        assert audit_log.success is True, "Audit log should mark success as True"
                        if user:
                            assert audit_log.user_id == user.id, f"Audit log should mark the organization admin as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_3_8_org_admin_cannot_update_alpha2_organization(self, authenticated_client, http_client):
        """Test Scenario 3.8: Org Admin Cannot Update Test Organization Alpha2"""
        email, password = get_user_credentials("Account 1 Org Admin")
        client = authenticated_client(email, password)
        
        # Account 1 Org Admin should not have access to Test Organization Alpha2
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha2").first()
            if org:
                payload = {
                    "account": org.account.id,
                    "name": org.name,
                    "description": "Unauthorized update attempt"
                }
                before_request = timezone.now() - timedelta(seconds=5)
                response = make_request(client, "put", f"/organizations/{org.uuid}/", json=payload)
                
                assert response.status_code == 403, \
                    f"Expected 403 for org admin updating Alpha2, got {response.status_code}, response: {response.text}"
                data = response.json()
                assert data.get("code") == "INSUFFICIENT_PERMISSIONS", \
                    f"Response should indicate insufficient permissions, got {data}"
                
                # Verify audit log
                if DJANGO_AVAILABLE and AuditLog:
                    user = User.objects.using('default').filter(email=email).first()
                    audit_log = AuditLog.objects.using('default').filter(
                        path=f"/api/organizations/{org.uuid}/",
                        method="PUT",
                        status_code=403,
                        created_at__gte=before_request
                    ).order_by("-created_at").first()
                    assert audit_log is not None, "Audit log entry should be created"
                    assert audit_log.success is False, "Audit log should mark success as False"
                    if user:
                        assert audit_log.user_id == user.id, \
                            f"Audit log should reference user: {audit_log.user_id} != {user.id}"


@pytest.mark.acceptance
class TestREQOrg004DeactivateOrganization:
    """REQ-ORG-004: Deactivate Organization"""

    def test_4_1_deactivate_organization_by_account_owner_no_subscriptions(self, authenticated_client, http_client):
        """Test Scenario 4.1: Happy Path"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get organization without active subscriptions
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha3").first()
            if org:
                # Ensure organization is active
                org.is_active = True
                org.save()
                
                response = make_request(client, "post", f"/organizations/{org.uuid}/deactivate/")
                
                assert response.status_code == 200, \
                    f"Expected 200 but got {response.status_code}, response: {response.text}"
                data = response.json()
                assert data.get("is_active") is False, "Organization should be deactivated"
                
                # Verify in database
                org.refresh_from_db()
                assert org.is_active is False, "Organization should be inactive in database"
                
                # Verify audit log
                if DJANGO_AVAILABLE and AuditLog:
                    user = User.objects.using('default').filter(email=email).first()
                    audit_log = AuditLog.objects.using('default').filter(
                        path=f"/api/organizations/{org.uuid}/deactivate/",
                        method="POST",
                        status_code=200,
                        created_at__gte=timezone.now() - timedelta(seconds=5)
                    ).order_by("-created_at").first()
                    assert audit_log is not None, "Audit log entry should be created"
                    assert audit_log.success is True, "Audit log should mark success as True"
                    if user:
                        assert audit_log.user_id == user.id, f"Audit log should mark the account owner as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_4_2_deactivate_organization_by_account_admin(self, authenticated_client, http_client):
        """Test Scenario 4.2: Account Admin"""
        email, password = get_user_credentials("Account 1 Admin")
        client = authenticated_client(email, password)
        
        # Get organization in account
        if DJANGO_AVAILABLE and Organization and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                user_org = UserOrganization.objects.using('default').filter(user=user).first()
                if user_org and user_org.organization:
                    account = user_org.organization.account
                    org = Organization.objects.using('default').filter(
                        account=account,
                        name="Test Organization Alpha3"
                    ).first()
                    if org:
                        org.is_active = True
                        org.save()
                        
                        response = make_request(client, "post", f"/organizations/{org.uuid}/deactivate/")
                        
                        assert response.status_code == 200, \
                            f"Expected 200 but got {response.status_code}, response: {response.text}"

    def test_4_3_deactivate_organization_by_saas_account_manager(self, authenticated_client, http_client):
        """Test Scenario 4.3: SaaS Account Manager"""
        email, password = get_user_credentials("SaaS Account Manager")
        client = authenticated_client(email, password)
        
        # Get organization in assigned account
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha3").first()
            if org:
                org.is_active = True
                org.save()
                
                response = make_request(client, "post", f"/organizations/{org.uuid}/deactivate/")
                
                assert response.status_code == 200, \
                    f"Expected 200 but got {response.status_code}, response: {response.text}"

    def test_4_4_deactivate_organization_with_active_subscriptions(self, authenticated_client, http_client):
        """Test Scenario 4.4: With Subscriptions"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get organization with active subscriptions
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if org:
                # Check if organization has active subscriptions
                has_active_subscriptions = False
                if Subscription:
                    has_active_subscriptions = Subscription.objects.using('default').filter(
                        organization=org,
                        is_active=True
                    ).exists()
                
                if has_active_subscriptions:
                    response = make_request(client, "post", f"/organizations/{org.uuid}/deactivate/")
                    
                    assert response.status_code == 400, \
                        f"Expected 400 for organization with active subscriptions, got {response.status_code}, response: {response.text}"
                    data = response.json()
                    assert "subscription" in str(data).lower() or "code" in data, \
                        f"Response should indicate active subscriptions, got {data}"
                    assert data.get("code") == "ORGANIZATION_HAS_ACTIVE_SUBSCRIPTIONS"
                    if DJANGO_AVAILABLE and AuditLog:
                        user = User.objects.using('default').filter(email=email).first()
                        audit_log = AuditLog.objects.using('default').filter(
                            path=f"/api/organizations/{org.uuid}/deactivate/",
                            method="POST",
                            status_code=400,
                            created_at__gte=timezone.now() - timedelta(seconds=5)
                        ).order_by("-created_at").first()
                        assert audit_log is not None, "Audit log entry should be created"
                        assert audit_log.success is False, "Audit log should mark success as False"
                        if user:
                            assert audit_log.user_id == user.id, f"Audit log should mark the account owner as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_4_5_deactivate_organization_unauthorized(self, authenticated_client, http_client):
        """Test Scenario 4.5: Unauthorized Deactivation"""
        email, password = get_user_credentials("Account 1 User 1")
        client = authenticated_client(email, password)
        
        # Regular member should not be able to deactivate
        if DJANGO_AVAILABLE and Organization and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                user_org = UserOrganization.objects.using('default').filter(user=user).first()
                if user_org and user_org.organization:
                    org = user_org.organization
                    response = make_request(client, "post", f"/organizations/{org.uuid}/deactivate/")
                    
                    assert response.status_code == 403, \
                        f"Expected 403 for unauthorized deactivation, got {response.status_code}, response: {response.text}"
                    data = response.json()
                    assert data.get("code") == "INSUFFICIENT_PERMISSIONS"
                    if DJANGO_AVAILABLE and AuditLog:
                        user = User.objects.using('default').filter(email=email).first()
                        audit_log = AuditLog.objects.using('default').filter(
                            path=f"/api/organizations/{org.uuid}/deactivate/",
                            method="POST",
                            status_code=403,
                            created_at__gte=timezone.now() - timedelta(seconds=5)
                        ).order_by("-created_at").first()
                        assert audit_log is not None, "Audit log entry should be created"
                        assert audit_log.success is False, "Audit log should mark success as False"
                        if user:
                            assert audit_log.user_id == user.id, f"Audit log should mark the organization member as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_4_6_deactivate_nonexistent_organization(self, authenticated_client, http_client):
        """Test Scenario 4.6: Deactivate Non-Existent Organization"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        fake_uuid = str(uuid.uuid4())
        response = make_request(client, "post", f"/organizations/{fake_uuid}/deactivate/")
        
        assert response.status_code == 404, \
            f"Expected 404 for non-existent organization, got {response.status_code}, response: {response.text}"

    def test_4_7_org_admin_cannot_deactivate_alpha2_organization(self, authenticated_client, http_client):
        """Test Scenario 4.7: Org Admin Cannot Deactivate Test Organization Alpha2"""
        email, password = get_user_credentials("Account 1 Org Admin")
        client = authenticated_client(email, password)
        
        # Account 1 Org Admin should not have access to Test Organization Alpha2
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha2").first()
            if org:
                before_request = timezone.now() - timedelta(seconds=5)
                response = make_request(client, "post", f"/organizations/{org.uuid}/deactivate/")
                
                assert response.status_code == 403, \
                    f"Expected 403 for org admin deactivating Alpha2, got {response.status_code}, response: {response.text}"
                data = response.json()
                assert data.get("code") == "INSUFFICIENT_PERMISSIONS", \
                    f"Response should indicate insufficient permissions, got {data}"
                
                # Verify audit log
                if DJANGO_AVAILABLE and AuditLog:
                    user = User.objects.using('default').filter(email=email).first()
                    audit_log = AuditLog.objects.using('default').filter(
                        path=f"/api/organizations/{org.uuid}/deactivate/",
                        method="POST",
                        status_code=403,
                        created_at__gte=before_request
                    ).order_by("-created_at").first()
                    assert audit_log is not None, "Audit log entry should be created"
                    assert audit_log.success is False, "Audit log should mark success as False"
                    if user:
                        assert audit_log.user_id == user.id, \
                            f"Audit log should reference user: {audit_log.user_id} != {user.id}"


@pytest.mark.acceptance
class TestREQOrg005DeleteOrganization:
    """REQ-ORG-005: Delete Organization (Soft Delete)"""

    def test_5_1_delete_organization_by_account_owner_no_subscriptions(self, authenticated_client, http_client):
        """Test Scenario 5.1: Happy Path"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Create a temporary organization for deletion
        if DJANGO_AVAILABLE and Account and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                account = Account.objects.using('default').filter(created_by=user).first()
                if account:
                    # Create organization
                    timestamp = int(time.time())
                    create_payload = {
                        "account": account.id,
                        "name": f"Delete Test Org {timestamp}"
                    }
                    create_response = make_request(client, "post", "/organizations/", json=create_payload)
                    assert create_response.status_code == 201
                    org_uuid = create_response.json().get("uuid") or create_response.json().get("id")
                    
                    # Delete organization
                    response = make_request(client, "delete", f"/organizations/{org_uuid}/")
                    
                    assert response.status_code == 204, \
                        f"Expected 204 but got {response.status_code}, response: {response.text}"
                    
                    # Verify soft delete in database
                    if DJANGO_AVAILABLE and Organization:
                        org = Organization.objects.using('default').filter(uuid=org_uuid).first()
                        if org:
                            assert org.deleted_at is not None, "Organization should have deleted_at set"
                    
                    # Verify audit log
                    if DJANGO_AVAILABLE and AuditLog:
                        user = User.objects.using('default').filter(email=email).first()
                        audit_log = AuditLog.objects.using('default').filter(
                            path=f"/api/organizations/{org_uuid}/",
                            method="DELETE",
                            status_code=204,
                            created_at__gte=timezone.now() - timedelta(seconds=5)
                        ).order_by("-created_at").first()
                        assert audit_log is not None, "Audit log entry should be created"
                        assert audit_log.success is True, "Audit log should mark success as True"
                        if user:
                            assert audit_log.user_id == user.id, f"Audit log should mark the account owner as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_5_2_delete_organization_by_account_admin(self, authenticated_client, http_client):
        """Test Scenario 5.2: Account Admin"""
        email, password = get_user_credentials("Account 1 Admin")
        client = authenticated_client(email, password)
        
        # Create organization for deletion
        if DJANGO_AVAILABLE and Account and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                user_org = UserOrganization.objects.using('default').filter(user=user).first()
                if user_org and user_org.organization:
                    account = user_org.organization.account
                    timestamp = int(time.time())
                    create_payload = {
                        "account": account.id,
                        "name": f"Admin Delete Test {timestamp}"
                    }
                    create_response = make_request(client, "post", "/organizations/", json=create_payload)
                    assert create_response.status_code == 201
                    org_uuid = create_response.json().get("uuid") or create_response.json().get("id")
                    
                    # Delete organization
                    response = make_request(client, "delete", f"/organizations/{org_uuid}/")
                    
                    assert response.status_code == 204, \
                        f"Expected 204 but got {response.status_code}, response: {response.text}"

    def test_5_3_delete_organization_by_saas_account_manager(self, authenticated_client, http_client):
        """Test Scenario 5.3: SaaS Account Manager"""
        email, password = get_user_credentials("SaaS Account Manager")
        client = authenticated_client(email, password)
        
        # Create organization in assigned account
        admin_email, admin_password = get_user_credentials("Super Admin")
        admin_client = authenticated_client(admin_email, admin_password)
        
        if DJANGO_AVAILABLE and Account:
            account = Account.objects.using('default').filter(name="Test Account Alpha").first()
            if account:
                # Get a user to assign as owner
                owner_email, _ = get_user_credentials("Account 1 User 1")

                owner_user = User.objects.using('default').filter(email=owner_email).first()
                
                if owner_user:
                    timestamp = int(time.time())
                    create_payload = {
                        "account": account.id,
                        "name": f"Manager Delete Test {timestamp}",
                        "owner": owner_user.id
                    }
                    create_response = make_request(admin_client, "post", "/organizations/", json=create_payload)
                    assert create_response.status_code == 201
                    org_uuid = create_response.json().get("uuid") or create_response.json().get("id")
                    
                    # Delete organization
                    response = make_request(client, "delete", f"/organizations/{org_uuid}/")
                    
                    # Should succeed if account is assigned
                    assert response.status_code in (204, 403), \
                        f"Expected 204 or 403, got {response.status_code}, response: {response.text}"

    def test_5_4_delete_organization_with_active_subscriptions(self, authenticated_client, http_client):
        """Test Scenario 5.4: With Subscriptions"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get organization with active subscriptions
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if org:
                has_active_subscriptions = False
                if Subscription:
                    has_active_subscriptions = Subscription.objects.using('default').filter(
                        organization=org,
                        is_active=True
                    ).exists()
                
                if has_active_subscriptions:
                    response = make_request(client, "delete", f"/organizations/{org.uuid}/")
                    
                    assert response.status_code == 400, \
                        f"Expected 400 for organization with active subscriptions, got {response.status_code}, response: {response.text}"

    def test_5_5_access_deleted_organization(self, authenticated_client, http_client):
        """Test Scenario 5.5: Access after Delete"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Create and delete organization
        if DJANGO_AVAILABLE and Account and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                account = Account.objects.using('default').filter(created_by=user).first()
                if account:
                    timestamp = int(time.time())
                    create_payload = {
                        "account": account.id,
                        "name": f"Access Deleted Test {timestamp}"
                    }
                    create_response = make_request(client, "post", "/organizations/", json=create_payload)
                    assert create_response.status_code == 201
                    org_uuid = create_response.json().get("uuid") or create_response.json().get("id")
                    
                    # Delete organization
                    delete_response = make_request(client, "delete", f"/organizations/{org_uuid}/")
                    assert delete_response.status_code == 204
                    
                    # Try to access deleted organization
                    get_response = make_request(client, "get", f"/organizations/{org_uuid}/")
                    assert get_response.status_code == 404, \
                        f"Expected 404 for deleted organization, got {get_response.status_code}, response: {get_response.text}"
                    data = get_response.json()
                    assert data.get("code") == "ORGANIZATION_NOT_FOUND"

    def test_5_6_delete_organization_unauthorized(self, authenticated_client, http_client):
        """Test Scenario 5.6: Unauthorized Deletion"""
        email, password = get_user_credentials("Account 1 User 1")
        client = authenticated_client(email, password)
        
        # Regular member should not be able to delete
        if DJANGO_AVAILABLE and Organization and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                user_org = UserOrganization.objects.using('default').filter(user=user).first()
                if user_org and user_org.organization:
                    org = user_org.organization
                    response = make_request(client, "delete", f"/organizations/{org.uuid}/")
                    
                    assert response.status_code == 403, \
                        f"Expected 403 for unauthorized deletion, got {response.status_code}, response: {response.text}"
                    data = response.json()
                    assert data.get("code") == "INSUFFICIENT_PERMISSIONS"
                    if DJANGO_AVAILABLE and AuditLog:
                        user = User.objects.using('default').filter(email=email).first()
                        audit_log = AuditLog.objects.using('default').filter(
                            path=f"/api/organizations/{org.uuid}/",
                            method="DELETE",
                            status_code=403,
                            created_at__gte=timezone.now() - timedelta(seconds=5)
                        ).order_by("-created_at").first()
                        assert audit_log is not None, "Audit log entry should be created"
                        assert audit_log.success is False, "Audit log should mark success as False"
                        if user:
                            assert audit_log.user_id == user.id, f"Audit log should mark the organization member as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_5_7_delete_nonexistent_organization(self, authenticated_client, http_client):
        """Test Scenario 5.7: Delete Non-Existent Organization"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        fake_uuid = str(uuid.uuid4())
        response = make_request(client, "delete", f"/organizations/{fake_uuid}/")
        
        assert response.status_code == 404, \
            f"Expected 404 for non-existent organization, got {response.status_code}, response: {response.text}"

    def test_5_8_org_admin_cannot_delete_alpha2_organization(self, authenticated_client, http_client):
        """Test Scenario 5.8: Org Admin Cannot Delete Test Organization Alpha2"""
        email, password = get_user_credentials("Account 1 Org Admin")
        client = authenticated_client(email, password)
        
        # Account 1 Org Admin should not have access to Test Organization Alpha2
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha2").first()
            if org:
                before_request = timezone.now() - timedelta(seconds=5)
                response = make_request(client, "delete", f"/organizations/{org.uuid}/")
                
                assert response.status_code == 403, \
                    f"Expected 403 for org admin deleting Alpha2, got {response.status_code}, response: {response.text}"
                data = response.json()
                assert data.get("code") == "INSUFFICIENT_PERMISSIONS", \
                    f"Response should indicate insufficient permissions, got {data}"
                
                # Verify audit log
                if DJANGO_AVAILABLE and AuditLog:
                    user = User.objects.using('default').filter(email=email).first()
                    audit_log = AuditLog.objects.using('default').filter(
                        path=f"/api/organizations/{org.uuid}/",
                        method="DELETE",
                        status_code=403,
                        created_at__gte=before_request
                    ).order_by("-created_at").first()
                    assert audit_log is not None, "Audit log entry should be created"
                    assert audit_log.success is False, "Audit log should mark success as False"
                    if user:
                        assert audit_log.user_id == user.id, \
                            f"Audit log should reference user: {audit_log.user_id} != {user.id}"


@pytest.mark.acceptance
class TestREQOrg006ListOrganizationsWithPagination:
    """REQ-ORG-006: List Organizations with Pagination"""

    def test_6_1_list_organizations_by_account_owner(self, authenticated_client, http_client):
        """Test Scenario 6.1: Account Owner"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        start_time = time.time()
        response = make_request(client, "get", "/organizations/")
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
                # Verify organizations belong to user's account
                if DJANGO_AVAILABLE and Account and User:
    
                    user = User.objects.using('default').filter(email=email).first()
                    if user:
                        account = Account.objects.using('default').filter(created_by=user).first()
                        if account:
                            for org_data in data["results"]:
                                assert org_data.get("account") == account.id, \
                                    "All organizations should belong to user's account"

    def test_6_2_list_organizations_by_account_admin(self, authenticated_client, http_client):
        """Test Scenario 6.2: Account Admin"""
        email, password = get_user_credentials("Account 1 Admin")
        client = authenticated_client(email, password)
        
        response = make_request(client, "get", "/organizations/")
        assert response.status_code == 200, f"Expected 200 but got {response.status_code}, response: {response.text}"

    def test_6_3_list_organizations_by_saas_account_manager(self, authenticated_client, http_client):
        """Test Scenario 6.3: SaaS Account Manager"""
        email, password = get_user_credentials("SaaS Account Manager")
        client = authenticated_client(email, password)
        
        response = make_request(client, "get", "/organizations/")
        assert response.status_code == 200, f"Expected 200 but got {response.status_code}, response: {response.text}"
        data = response.json()
        
        # Get results
        if isinstance(data, dict) and "results" in data:
            organizations = data["results"]
        elif isinstance(data, list):
            organizations = data
        else:
            organizations = []
        
        # Verify only organizations in assigned accounts are returned
        # SaaS Account Manager should only see organizations in Test Account Alpha and Test Account Gama
        if DJANGO_AVAILABLE and Account:
            assigned_accounts = Account.objects.using('default').filter(
                name__in=["Test Account Alpha", "Test Account Gama"]
            )
            assigned_account_ids = [acc.id for acc in assigned_accounts]
            
            for org_data in organizations:
                assert org_data.get("account") in assigned_account_ids, \
                    "Should only see organizations in assigned accounts"

    def test_6_4_list_organizations_by_saas_admin(self, authenticated_client, http_client):
        """Test Scenario 6.4: SaaS Admin"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        response = make_request(client, "get", "/organizations/")
        assert response.status_code == 200, f"Expected 200 but got {response.status_code}, response: {response.text}"

    def test_6_5_list_organizations_with_invalid_pagination(self, authenticated_client, http_client):
        """Test Scenario 6.5: Invalid Pagination"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Test invalid pagination parameters
        invalid_params = [
            ("?page=0", 400),
            ("?page_size=0", 400),
            ("?page=-1", 400),
        ]
        
        for params, expected_status in invalid_params:
            response = make_request(client, "get", f"/organizations/{params}")
            assert response.status_code == expected_status or response.status_code == 200, \
                f"Expected {expected_status} or 200 for invalid params '{params}', got {response.status_code}"

    def test_6_6_list_organizations_with_filtering(self, authenticated_client, http_client):
        """Test Scenario 6.6: List Organizations with Filtering"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get account ID for filtering
        if DJANGO_AVAILABLE and Account and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                account = Account.objects.using('default').filter(created_by=user).first()
                if account:
                    # Test filtering by account
                    response = make_request(client, "get", f"/organizations/?account={account.id}")
                    assert response.status_code == 200
                    
                    # Test filtering by is_active
                    response_active = make_request(client, "get", f"/organizations/?is_active=true")
                    assert response_active.status_code == 200
                    
                    response_inactive = make_request(client, "get", f"/organizations/?is_active=false")
                    assert response_inactive.status_code == 200

    def test_6_7_list_organizations_with_ordering(self, authenticated_client, http_client):
        """Test Scenario 6.7: List Organizations with Ordering"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Test ordering by name
        response_asc = make_request(client, "get", "/organizations/?ordering=name")
        assert response_asc.status_code == 200
        
        response_desc = make_request(client, "get", "/organizations/?ordering=-name")
        assert response_desc.status_code == 200

    def test_6_8_list_organizations_unauthenticated(self, http_client):
        """Test Scenario 6.8: List Organizations Unauthenticated"""
        response = make_request(http_client, "get", "/organizations/")
        
        assert response.status_code == 401, \
            f"Expected 401 for unauthenticated request, got {response.status_code}, response: {response.text}"

    def test_6_9_org_admin_cannot_see_alpha2_in_list(self, authenticated_client, http_client):
        """Test Scenario 6.9: Org Admin Cannot See Test Organization Alpha2 in List"""
        email, password = get_user_credentials("Account 1 Org Admin")
        client = authenticated_client(email, password)
        
        # Account 1 Org Admin should not see Test Organization Alpha2 in the list
        if DJANGO_AVAILABLE and Organization:
            before_request = timezone.now() - timedelta(seconds=5)
            response = make_request(client, "get", "/organizations/")
            
            assert response.status_code == 200, \
                f"Expected 200 but got {response.status_code}, response: {response.text}"
            data = response.json()
            
            # Get results
            if isinstance(data, dict) and "results" in data:
                organizations = data["results"]
            elif isinstance(data, list):
                organizations = data
            else:
                organizations = []
            
            # Verify Alpha2 is not in the list
            org_names = [org.get("name", "") for org in organizations]
            assert "Test Organization Alpha2" not in org_names, \
                "Account 1 Org Admin should not see Test Organization Alpha2 in the list"
            
            # Verify audit log
            if DJANGO_AVAILABLE and AuditLog:
                user = User.objects.using('default').filter(email=email).first()
                audit_log = AuditLog.objects.using('default').filter(
                    path="/api/organizations/",
                    method="GET",
                    status_code=200,
                    created_at__gte=before_request
                ).order_by("-created_at").first()
                assert audit_log is not None, "Audit log entry should be created"
                assert audit_log.success is True, "Audit log should mark success as True"
                if user:
                    assert audit_log.user_id == user.id, \
                        f"Audit log should reference user: {audit_log.user_id} != {user.id}"


@pytest.mark.acceptance
class TestREQOrg007AssignOrganizationOwner:
    """REQ-ORG-007: Assign Organization Owner"""

    def test_7_1_assign_organization_owner_by_account_owner(self, authenticated_client, http_client):
        """Test Scenario 7.1: Happy Path"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get organization in account
        if DJANGO_AVAILABLE and Organization and Account and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                account = Account.objects.using('default').filter(created_by=user).first()
                if account:
                    org = Organization.objects.using('default').filter(account=account).first()
                    if org:
                        # Get a member user to assign as owner
                        member_email, _ = get_user_credentials("Account 1 User 1")
                        member_user = User.objects.using('default').filter(email=member_email).first()
                        
                        if member_user:
                            # Ensure user is a member of the organization
                            user_org, created = UserOrganization.objects.using('default').get_or_create(
                                user=member_user,
                                organization=org
                            )
                            
                            payload = {
                                "user_id": member_user.id
                            }
                            
                            response = make_request(client, "post", f"/organizations/{org.uuid}/assign-owner/", json=payload)
                            
                            assert response.status_code == 200, \
                                f"Expected 200 but got {response.status_code}, response: {response.text}"
                            if DJANGO_AVAILABLE and AuditLog:
                                user = User.objects.using('default').filter(email=email).first()
                                audit_log = AuditLog.objects.using('default').filter(
                                    path=f"/api/organizations/{org.uuid}/assign-owner/",
                                    method="POST",
                                    status_code=200,
                                    created_at__gte=timezone.now() - timedelta(seconds=5)
                                ).order_by("-created_at").first()
                                assert audit_log is not None, "Audit log entry should be created"
                                assert audit_log.success is True, "Audit log should mark success as True"
                                if user:
                                    assert audit_log.user_id == user.id, f"Audit log should mark the account owner as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_7_2_assign_organization_owner_non_member(self, authenticated_client, http_client):
        """Test Scenario 7.2: Non-Member"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get organization in account
        if DJANGO_AVAILABLE and Organization and Account and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                account = Account.objects.using('default').filter(created_by=user).first()
                if account:
                    org = Organization.objects.using('default').filter(account=account).first()
                    if org:
                        # Get a user who is not a member
                        non_member_email, _ = get_user_credentials("Account 1 User 3")
                        non_member_user = User.objects.using('default').filter(email=non_member_email).first()
                        
                        if non_member_user:
                            # Ensure user is NOT a member
                            UserOrganization.objects.using('default').filter(
                                user=non_member_user,
                                organization=org
                            ).delete()
                            
                            payload = {
                                "user_id": non_member_user.id
                            }
                            
                            response = make_request(client, "post", f"/organizations/{org.uuid}/assign-owner/", json=payload)
                            
                            assert response.status_code == 400, \
                                f"Expected 400 for non-member, got {response.status_code}, response: {response.text}"
                            data = response.json()
                            assert "member" in str(data).lower() or "code" in data, \
                                f"Response should indicate user is not a member, got {data}"
                            assert data.get("code") == "USER_NOT_ORGANIZATION_MEMBER" or "member" in str(data).lower()
                            if DJANGO_AVAILABLE and AuditLog:
                                user = User.objects.using('default').filter(email=email).first()
                                audit_log = AuditLog.objects.using('default').filter(
                                    path=f"/api/organizations/{org.uuid}/assign-owner/",
                                    method="POST",
                                    status_code=400,
                                    created_at__gte=timezone.now() - timedelta(seconds=5)
                                ).order_by("-created_at").first()
                                assert audit_log is not None, "Audit log entry should be created"
                                assert audit_log.success is False, "Audit log should mark success as False"
                                if user:
                                    assert audit_log.user_id == user.id, f"Audit log should mark the account owner as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_7_3_assign_organization_owner_previous_owner(self, authenticated_client, http_client):
        """Test Scenario 7.3: Previous Owner"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get organization in account
        if DJANGO_AVAILABLE and Organization and Account and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                account = Account.objects.using('default').filter(created_by=user).first()
                if account:
                    org = Organization.objects.using('default').filter(account=account).first()
                    if org:
                        # Get a member user to assign as owner
                        member_email, _ = get_user_credentials("Account 1 User 1")
                        member_user = User.objects.using('default').filter(email=member_email).first()
                        
                        if member_user:
                            # Ensure user is a member
                            user_org, created = UserOrganization.objects.using('default').get_or_create(
                                user=member_user,
                                organization=org
                            )
                            
                            payload = {
                                "user_id": member_user.id
                            }
                            
                            # Assign owner
                            response1 = make_request(client, "post", f"/organizations/{org.uuid}/assign-owner/", json=payload)
                            assert response1.status_code == 200
                            
                            # Previous owner should retain other roles but lose owner privileges
                            # This would need to be verified by checking role assignments

    def test_7_4_assign_organization_owner_unauthorized(self, authenticated_client, http_client):
        """Test Scenario 7.4: Unauthorized Assignment"""
        email, password = get_user_credentials("Account 1 User 1")
        client = authenticated_client(email, password)
        
        # Regular member should not be able to assign owner
        if DJANGO_AVAILABLE and Organization and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                user_org = UserOrganization.objects.using('default').filter(user=user).first()
                if user_org and user_org.organization:
                    org = user_org.organization
                    payload = {
                        "user_id": user.id
                    }
                    
                    response = make_request(client, "post", f"/organizations/{org.uuid}/assign-owner/", json=payload)
                    
                    assert response.status_code == 403, \
                        f"Expected 403 for unauthorized assignment, got {response.status_code}, response: {response.text}"
                    data = response.json()
                    assert data.get("code") == "INSUFFICIENT_PERMISSIONS"
                    if DJANGO_AVAILABLE and AuditLog:
                        user = User.objects.using('default').filter(email=email).first()
                        audit_log = AuditLog.objects.using('default').filter(
                            path=f"/api/organizations/{org.uuid}/assign-owner/",
                            method="POST",
                            status_code=403,
                            created_at__gte=timezone.now() - timedelta(seconds=5)
                        ).order_by("-created_at").first()
                        assert audit_log is not None, "Audit log entry should be created"
                        assert audit_log.success is False, "Audit log should mark success as False"
                        if user:
                            assert audit_log.user_id == user.id, f"Audit log should mark the organization member as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_7_5_org_admin_cannot_assign_alpha2_owner(self, authenticated_client, http_client):
        """Test Scenario 7.5: Org Admin Cannot Assign Owner to Test Organization Alpha2"""
        email, password = get_user_credentials("Account 1 Org Admin")
        client = authenticated_client(email, password)
        
        # Account 1 Org Admin should not have access to Test Organization Alpha2
        if DJANGO_AVAILABLE and Organization and User:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha2").first()
            if org:
                member_email, _ = get_user_credentials("Account 1 User 1")
                member_user = User.objects.using('default').filter(email=member_email).first()
                
                if member_user:
                    payload = {
                        "user_id": member_user.id
                    }
                    before_request = timezone.now() - timedelta(seconds=5)
                    response = make_request(client, "post", f"/organizations/{org.uuid}/assign-owner/", json=payload)
                    
                    assert response.status_code == 403, \
                        f"Expected 403 for org admin assigning Alpha2 owner, got {response.status_code}, response: {response.text}"
                    data = response.json()
                    assert data.get("code") == "INSUFFICIENT_PERMISSIONS", \
                        f"Response should indicate insufficient permissions, got {data}"
                    
                    # Verify audit log
                    if DJANGO_AVAILABLE and AuditLog:
                        user = User.objects.using('default').filter(email=email).first()
                        audit_log = AuditLog.objects.using('default').filter(
                            path=f"/api/organizations/{org.uuid}/assign-owner/",
                            method="POST",
                            status_code=403,
                            created_at__gte=before_request
                        ).order_by("-created_at").first()
                        assert audit_log is not None, "Audit log entry should be created"
                        assert audit_log.success is False, "Audit log should mark success as False"
                        if user:
                            assert audit_log.user_id == user.id, \
                                f"Audit log should reference user: {audit_log.user_id} != {user.id}"


@pytest.mark.acceptance
class TestREQOrg008TransferOrganizationOwnership:
    """REQ-ORG-008: Transfer Organization Ownership"""

    def test_8_1_transfer_ownership_by_org_owner(self, authenticated_client, http_client):
        """Test Scenario 8.1: Org Owner"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get organization owned by this user
        if DJANGO_AVAILABLE and Organization and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                from apps.roles.models import RoleAssignment
                from apps.roles.constants import ROLE_ORGANIZATION_OWNER
                
                org_assignment = RoleAssignment.objects.using('default').filter(
                    user=user,
                    role__key=ROLE_ORGANIZATION_OWNER,
                    deleted_at__isnull=True
                ).first()
                
                if org_assignment and org_assignment.organization:
                    org = org_assignment.organization
                    # Get a member user to transfer to
                    member_email, _ = get_user_credentials("Account 1 User 1")
                    member_user = User.objects.using('default').filter(email=member_email).first()
                    
                    if member_user:
                        # Ensure user is a member
                        user_org, created = UserOrganization.objects.using('default').get_or_create(
                            user=member_user,
                            organization=org
                        )
                        
                        payload = {
                            "user_id": member_user.id
                        }
                        
                        response = make_request(client, "post", f"/organizations/{org.uuid}/transfer-owner/", json=payload)
                        
                        assert response.status_code == 200, \
                            f"Expected 200 but got {response.status_code}, response: {response.text}"

    def test_8_2_transfer_ownership_by_saas_account_manager(self, authenticated_client, http_client):
        """Test Scenario 8.2: SaaS Account Manager"""
        email, password = get_user_credentials("SaaS Account Manager")
        client = authenticated_client(email, password)
        
        # Get organization in assigned account
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if org:

                member_email, _ = get_user_credentials("Account 1 User 1")
                member_user = User.objects.using('default').filter(email=member_email).first()
                
                if member_user:
                    # Ensure user is a member
                    user_org, created = UserOrganization.objects.using('default').get_or_create(
                        user=member_user,
                        organization=org
                    )
                    
                    payload = {
                        "user_id": member_user.id
                    }
                    
                    response = make_request(client, "post", f"/organizations/{org.uuid}/transfer-owner/", json=payload)
                    
                    # Should succeed if account is assigned
                    assert response.status_code in (200, 403), \
                        f"Expected 200 or 403, got {response.status_code}, response: {response.text}"

    def test_8_3_transfer_ownership_by_saas_admin(self, authenticated_client, http_client):
        """Test Scenario 8.3: SaaS Admin"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get any organization
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if org:

                member_email, _ = get_user_credentials("Account 1 User 1")
                member_user = User.objects.using('default').filter(email=member_email).first()
                
                if member_user:
                    # Ensure user is a member
                    user_org, created = UserOrganization.objects.using('default').get_or_create(
                        user=member_user,
                        organization=org
                    )
                    
                    payload = {
                        "user_id": member_user.id
                    }
                    
                    response = make_request(client, "post", f"/organizations/{org.uuid}/transfer-owner/", json=payload)
                    
                    assert response.status_code == 200, \
                        f"Expected 200 but got {response.status_code}, response: {response.text}"

    def test_8_4_transfer_ownership_non_member(self, authenticated_client, http_client):
        """Test Scenario 8.4: Non-Member"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get organization owned by this user
        if DJANGO_AVAILABLE and Organization and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                from apps.roles.models import RoleAssignment
                from apps.roles.constants import ROLE_ORGANIZATION_OWNER
                
                org_assignment = RoleAssignment.objects.using('default').filter(
                    user=user,
                    role__key=ROLE_ORGANIZATION_OWNER,
                    deleted_at__isnull=True
                ).first()
                
                if org_assignment and org_assignment.organization:
                    org = org_assignment.organization
                    # Get a user who is not a member
                    non_member_email, _ = get_user_credentials("Account 1 User 3")
                    non_member_user = User.objects.using('default').filter(email=non_member_email).first()
                    
                    if non_member_user:
                        # Ensure user is NOT a member
                        UserOrganization.objects.using('default').filter(
                            user=non_member_user,
                            organization=org
                        ).delete()
                        
                        payload = {
                            "user_id": non_member_user.id
                        }
                        
                        response = make_request(client, "post", f"/organizations/{org.uuid}/transfer-owner/", json=payload)
                        
                        assert response.status_code == 400, \
                            f"Expected 400 for non-member, got {response.status_code}, response: {response.text}"
                        data = response.json()
                        assert "member" in str(data).lower() or "code" in data, \
                            f"Response should indicate user is not a member, got {data}"
                        assert data.get("code") == "USER_NOT_ORGANIZATION_MEMBER" or "member" in str(data).lower()
                        if DJANGO_AVAILABLE and AuditLog:
                            user = User.objects.using('default').filter(email=email).first()
                            audit_log = AuditLog.objects.using('default').filter(
                                path=f"/api/organizations/{org.uuid}/transfer-owner/",
                                method="POST",
                                status_code=400,
                                created_at__gte=timezone.now() - timedelta(seconds=5)
                            ).order_by("-created_at").first()
                            assert audit_log is not None, "Audit log entry should be created"
                            assert audit_log.success is False, "Audit log should mark success as False"
                            if user:
                                assert audit_log.user_id == user.id, f"Audit log should mark the organization owner as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_8_5_transfer_ownership_unauthorized_org_admin(self, authenticated_client, http_client):
        """Test Scenario 8.5: Unauthorized - Org Admin"""
        email, password = get_user_credentials("Account 1 Org Admin")
        client = authenticated_client(email, password)
        
        # Organization Admin should not be able to transfer ownership
        if DJANGO_AVAILABLE and Organization and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                user_org = UserOrganization.objects.using('default').filter(user=user).first()
                if user_org and user_org.organization:
                    org = user_org.organization
                    member_email, _ = get_user_credentials("Account 1 User 1")
                    member_user = User.objects.using('default').filter(email=member_email).first()
                    
                    if member_user:
                        payload = {
                            "user_id": member_user.id
                        }
                        
                        response = make_request(client, "post", f"/organizations/{org.uuid}/transfer-owner/", json=payload)
                        
                        assert response.status_code == 403, \
                            f"Expected 403 for unauthorized transfer, got {response.status_code}, response: {response.text}"
                        data = response.json()
                        assert data.get("code") == "INSUFFICIENT_PERMISSIONS"
                        if DJANGO_AVAILABLE and AuditLog:
                            user = User.objects.using('default').filter(email=email).first()
                            audit_log = AuditLog.objects.using('default').filter(
                                path=f"/api/organizations/{org.uuid}/transfer-owner/",
                                method="POST",
                                status_code=403,
                                created_at__gte=timezone.now() - timedelta(seconds=5)
                            ).order_by("-created_at").first()
                            assert audit_log is not None, "Audit log entry should be created"
                            assert audit_log.success is False, "Audit log should mark success as False"
                            if user:
                                assert audit_log.user_id == user.id, f"Audit log should mark the organization admin as user, expected: {user.id}, got: {audit_log.user_id}"

    def test_8_6_transfer_ownership_previous_owner(self, authenticated_client, http_client):
        """Test Scenario 8.6: Previous Owner"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get organization owned by this user
        if DJANGO_AVAILABLE and Organization and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                from apps.roles.models import RoleAssignment
                from apps.roles.constants import ROLE_ORGANIZATION_OWNER
                
                org_assignment = RoleAssignment.objects.using('default').filter(
                    user=user,
                    role__key=ROLE_ORGANIZATION_OWNER,
                    deleted_at__isnull=True
                ).first()
                
                if org_assignment and org_assignment.organization:
                    org = org_assignment.organization
                    # Get a member user to transfer to
                    member_email, _ = get_user_credentials("Account 1 User 1")
                    member_user = User.objects.using('default').filter(email=member_email).first()
                    
                    if member_user:
                        # Ensure user is a member
                        user_org, created = UserOrganization.objects.using('default').get_or_create(
                            user=member_user,
                            organization=org
                        )
                        
                        payload = {
                            "user_id": member_user.id
                        }
                        
                        # Transfer ownership
                        response = make_request(client, "post", f"/organizations/{org.uuid}/transfer-owner/", json=payload)
                        assert response.status_code == 200
                        
                        # Previous owner should retain other roles but lose owner privileges
                        # This would need to be verified by checking role assignments

    def test_8_7_transfer_ownership_nonexistent_organization(self, authenticated_client, http_client):
        """Test Scenario 8.7: Transfer Ownership of Non-Existent Organization"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        fake_uuid = str(uuid.uuid4())
        payload = {
            "user_id": 1
        }
        response = make_request(client, "post", f"/organizations/{fake_uuid}/transfer-owner/", json=payload)
        
        assert response.status_code == 404, \
            f"Expected 404 for non-existent organization, got {response.status_code}, response: {response.text}"

    def test_8_8_transfer_ownership_unauthenticated(self, http_client):
        """Test Scenario 8.8: Transfer Ownership Unauthenticated"""
        fake_uuid = str(uuid.uuid4())
        payload = {
            "user_id": 1
        }
        response = make_request(http_client, "post", f"/organizations/{fake_uuid}/transfer-owner/", json=payload)
        
        assert response.status_code == 401, \
            f"Expected 401 for unauthenticated request, got {response.status_code}, response: {response.text}"

    def test_8_9_org_admin_cannot_transfer_alpha2_ownership(self, authenticated_client, http_client):
        """Test Scenario 8.9: Org Admin Cannot Transfer Test Organization Alpha2 Ownership"""
        email, password = get_user_credentials("Account 1 Org Admin")
        client = authenticated_client(email, password)
        
        # Account 1 Org Admin should not have access to Test Organization Alpha2
        if DJANGO_AVAILABLE and Organization and User:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha2").first()
            if org:
                member_email, _ = get_user_credentials("Account 1 User 1")
                member_user = User.objects.using('default').filter(email=member_email).first()
                
                if member_user:
                    payload = {
                        "user_id": member_user.id
                    }
                    before_request = timezone.now() - timedelta(seconds=5)
                    response = make_request(client, "post", f"/organizations/{org.uuid}/transfer-owner/", json=payload)
                    
                    assert response.status_code == 403, \
                        f"Expected 403 for org admin transferring Alpha2 ownership, got {response.status_code}, response: {response.text}"
                    data = response.json()
                    assert data.get("code") == "INSUFFICIENT_PERMISSIONS", \
                        f"Response should indicate insufficient permissions, got {data}"
                    
                    # Verify audit log
                    if DJANGO_AVAILABLE and AuditLog:
                        user = User.objects.using('default').filter(email=email).first()
                        audit_log = AuditLog.objects.using('default').filter(
                            path=f"/api/organizations/{org.uuid}/transfer-owner/",
                            method="POST",
                            status_code=403,
                            created_at__gte=before_request
                        ).order_by("-created_at").first()
                        assert audit_log is not None, "Audit log entry should be created"
                        assert audit_log.success is False, "Audit log should mark success as False"
                        if user:
                            assert audit_log.user_id == user.id, \
                                f"Audit log should reference user: {audit_log.user_id} != {user.id}"


@pytest.mark.acceptance
class TestREQOrg009InputValidation:
    """REQ-ORG-009: Input Validation for Organizations"""

    def test_9_1_organization_name_validation_allowed_characters(self, authenticated_client, http_client):
        """Test Scenario 9.1: Organization Name Validation - Allowed Characters"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get account
        if DJANGO_AVAILABLE and Account and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                account = Account.objects.using('default').filter(created_by=user).first()
                if account:
                    # Test valid names with allowed characters (alphanumeric and spaces)
                    valid_names = [
                        "Test Organization 123",
                        "Test Organization",
                        "Test123",
                        "Organization Test",
                        "Test Organization Alpha Beta"
                    ]
                    
                    for valid_name in valid_names:
                        payload = {
                            "account": account.id,
                            "name": valid_name
                        }
                        response = make_request(client, "post", "/organizations/", json=payload)
                        # Should succeed or fail for duplicate, but not for invalid characters
                        assert response.status_code in (201, 409), \
                            f"Valid name '{valid_name}' should be accepted, got {response.status_code}, response: {response.text}"

    def test_9_2_organization_name_validation_invalid_characters(self, authenticated_client, http_client):
        """Test Scenario 9.2: Organization Name Validation - Invalid Characters"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get account
        if DJANGO_AVAILABLE and Account and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                account = Account.objects.using('default').filter(created_by=user).first()
                if account:
                    # Test invalid names with disallowed characters
                    invalid_names = [
                        "Test@Organization",  # @ not allowed
                        "Test#Organization",  # # not allowed in name
                        "Test$Organization",  # $ not allowed in name
                        "Test%Organization",  # % not allowed in name
                        "Test&Organization",  # & not allowed in name
                        "Test*Organization",  # * not allowed in name
                        "Test(Organization)",  # () not allowed in name
                        "Test-Organization",  # - not allowed in name
                    ]
                    
                    for invalid_name in invalid_names:
                        payload = {
                            "account": account.id,
                            "name": invalid_name
                        }
                        before_request = timezone.now() - timedelta(seconds=5)
                        response = make_request(client, "post", "/organizations/", json=payload)
                        
                        assert response.status_code == 400, \
                            f"Invalid name '{invalid_name}' should be rejected, got {response.status_code}, response: {response.text}"
                        data = response.json()
                        assert "name" in str(data).lower() or "invalid" in str(data).lower() or data.get("code") == "INVALID_ORGANIZATION_DATA", \
                            f"Response should indicate invalid name, got {data}"
                        
                        # Verify audit log
                        if DJANGO_AVAILABLE and AuditLog:
                            audit_log = AuditLog.objects.using('default').filter(
                                path="/api/organizations/",
                                method="POST",
                                status_code=400,
                                created_at__gte=before_request
                            ).order_by("-created_at").first()
                            if audit_log:
                                assert audit_log.success is False, "Audit log should mark success as False"

    def test_9_3_organization_name_validation_length(self, authenticated_client, http_client):
        """Test Scenario 9.3: Organization Name Validation - Length"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get account
        if DJANGO_AVAILABLE and Account and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                account = Account.objects.using('default').filter(created_by=user).first()
                if account:
                    # Test empty name
                    payload1 = {
                        "account": account.id,
                        "name": ""
                    }
                    response1 = make_request(client, "post", "/organizations/", json=payload1)
                    assert response1.status_code == 400, \
                        f"Expected 400 for empty name, got {response1.status_code}, response: {response1.text}"
                    
                    # Test name exceeding 100 characters
                    long_name = "A" * 101
                    payload2 = {
                        "account": account.id,
                        "name": long_name
                    }
                    response2 = make_request(client, "post", "/organizations/", json=payload2)
                    assert response2.status_code == 400, \
                        f"Expected 400 for name exceeding 100 chars, got {response2.status_code}, response: {response2.text}"
                    data2 = response2.json()
                    assert "name" in str(data2).lower() or "length" in str(data2).lower() or data2.get("code") == "INVALID_ORGANIZATION_DATA", \
                        f"Response should indicate invalid name length, got {data2}"

    def test_9_4_organization_description_validation_allowed_characters(self, authenticated_client, http_client):
        """Test Scenario 9.4: Organization Description Validation - Allowed Characters"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get account
        if DJANGO_AVAILABLE and Account and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                account = Account.objects.using('default').filter(created_by=user).first()
                if account:
                    # Test valid descriptions with allowed special characters
                    valid_descriptions = [
                        "Test description with allowed chars: ! * - ( ) # ? @ / ^ ~ . : ، ﷼ % & ' = + $ , [ ] ~",
                        "Test description\nwith newlines",
                        "Test description with spaces",
                        "Test description with numbers 123",
                    ]
                    
                    for valid_desc in valid_descriptions:
                        payload = {
                            "account": account.id,
                            "name": f"Test Org {int(time.time())}",
                            "description": valid_desc
                        }
                        response = make_request(client, "post", "/organizations/", json=payload)
                        # Should succeed
                        assert response.status_code == 201, \
                            f"Valid description should be accepted, got {response.status_code}, response: {response.text}"

    def test_9_5_organization_description_validation_length(self, authenticated_client, http_client):
        """Test Scenario 9.5: Organization Description Validation - Length"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get account
        if DJANGO_AVAILABLE and Account and User:
            user = User.objects.using('default').filter(email=email).first()
            if user:
                account = Account.objects.using('default').filter(created_by=user).first()
                if account:
                    # Test description exceeding 500 characters
                    long_description = "A" * 501
                    payload = {
                        "account": account.id,
                        "name": f"Test Org {int(time.time())}",
                        "description": long_description
                    }
                    response = make_request(client, "post", "/organizations/", json=payload)
                    assert response.status_code == 400, \
                        f"Expected 400 for description exceeding 500 chars, got {response.status_code}, response: {response.text}"
                    data = response.json()
                    assert "description" in str(data).lower() or "length" in str(data).lower() or data.get("code") == "INVALID_ORGANIZATION_DATA", \
                        f"Response should indicate invalid description length, got {data}"
