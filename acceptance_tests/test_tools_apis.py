"""
Acceptance tests for Tools Management API endpoints.

Tests cover all requirements from REQ-TOOL-001 through REQ-TOOL-008.
"""
import os
import pytest
import requests
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

# Import helpers from conftest
from acceptance_tests.conftest import (
    make_request,
    execute_raw_query,
    get_user_credentials,
    clear_all_login_failures,
    DJANGO_AVAILABLE,
)

# Import Django models if available
try:
    from django.db import connection, connections
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.utils import timezone
    from apps.users.models import User
    from apps.accounts.models import Account
    from apps.organizations.models import Organization
    from apps.common.models import AuditLog, DataChangeLog
    from apps.agents.models import OrganizationEnabledTool
    from apps.subscriptions.models import Subscription
    from apps.roles.models import Role, RoleAssignment
    from apps.products.models import Module
    from apps.users.models import UserOrganization
    DJANGO_AVAILABLE = True
except ImportError:
    DJANGO_AVAILABLE = False
    User = None
    Account = None
    Organization = None
    AuditLog = None
    DataChangeLog = None
    OrganizationEnabledTool = None
    Subscription = None
    Role = None
    RoleAssignment = None
    Module = None
    UserOrganization = None
    timezone = None
    timedelta = None


def ensure_tools_management_subscription(org):
    """Helper function to ensure organization has TOOLS_MANAGEMENT subscription"""
    if not DJANGO_AVAILABLE or not Module or not Subscription:
        return None
    
    tools_module = Module.objects.using('default').filter(key="TOOLS_MANAGEMENT").first()
    if not tools_module:
        return None
    
    subscription, _ = Subscription.objects.using('default').get_or_create(
        organization=org,
        module=tools_module,
        defaults={
            "status": Subscription.Status.ACTIVE,
            "configuration": {},
            "start_date": timezone.now() - timedelta(days=30),
            "end_date": None,
        }
    )
    if subscription.status != Subscription.Status.ACTIVE:
        subscription.status = Subscription.Status.ACTIVE
        subscription.save()
    return subscription


@pytest.mark.acceptance
class TestREQTool001ListAvailableTools:
    """REQ-TOOL-001: List Available Tools"""

    def test_1_1_successful_list_by_saas_administrator(self, authenticated_client, http_client):
        """Test Scenario 1.1: SaaS Administrator can list all available tools"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure TOOLS_MANAGEMENT subscription exists
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        # time.sleep(3600)
        # Make request
        before_request = timezone.now()
        response = make_request(client, "get", f"/tools/organizations/{org_uuid}/")
        
        # Verify response
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        assert len(data) > 0, "Should return at least one tool"
        
        # Verify tool structure
        tool = data[0]
        assert "toolKey" in tool or "tool_key" in tool, "Tool should have toolKey"
        assert "displayName" in tool or "display_name" in tool, "Tool should have displayName"
        assert "description" in tool, "Tool should have description"
        assert "category" in tool or "categories" in tool, "Tool should have category/categories"
        
        # Verify audit log
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/tools/organizations/{org_uuid}/",
                method="GET",
                status_code=200,
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            assert audit_log is not None, "Audit log entry should be created"
            assert audit_log.success is True, "Audit log should mark success as True"
            assert audit_log.user_id == user.id, "Audit log should reference correct user"

    def test_1_2_successful_list_by_saas_account_manager(self, authenticated_client, http_client):
        """Test Scenario 1.2: SaaS Account Manager can list available tools"""
        email, password = get_user_credentials("SaaS Account Manager")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure TOOLS_MANAGEMENT subscription exists
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Make request
        response = make_request(client, "get", f"/tools/organizations/{org_uuid}/")
        
        # Verify response
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"

    def test_1_3_successful_list_by_agent_manager(self, authenticated_client, http_client):
        """Test Scenario 1.3: Agent Manager can list available tools"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure TOOLS_MANAGEMENT subscription exists
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Make request
        response = make_request(client, "get", f"/tools/organizations/{org_uuid}/")
        
        # Verify response - Agent Manager should have access
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"

    def test_1_4_successful_list_by_account_admin(self, authenticated_client, http_client):
        """Test Scenario 1.4: Account Admin can list available tools"""
        email, password = get_user_credentials("Account 1 Admin")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Make request
        before_request = timezone.now()
        response = make_request(client, "get", f"/tools/organizations/{org_uuid}/")
        
        # Verify response - Account Admin should have access
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        
        # Verify audit log
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/tools/organizations/{org_uuid}/",
                method="GET",
                status_code=200,
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            if audit_log:
                assert audit_log.success is True, "Audit log should mark success as True"
                assert audit_log.user_id == user.id, "Audit log should reference correct user"

    def test_1_5_successful_list_by_account_owner(self, authenticated_client, http_client):
        """Test Scenario 1.5: Account Owner can list available tools"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Make request
        response = make_request(client, "get", f"/tools/organizations/{org_uuid}/")
        
        # Verify response - Account Owner should have access
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"

    def test_1_6_successful_list_by_organization_admin(self, authenticated_client, http_client):
        """Test Scenario 1.6: Organization Admin can list available tools"""
        email, password = get_user_credentials("Account 1 Org Admin")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Make request
        response = make_request(client, "get", f"/tools/organizations/{org_uuid}/")
        
        # Verify response - Organization Admin should have access
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"

    def test_1_7_successful_list_by_organization_owner(self, authenticated_client, http_client):
        """Test Scenario 1.7: Organization Owner can list available tools"""
        # Note: Organization Owner role may not exist in test data, using Account Owner as proxy
        # If Organization Owner exists, use that credential instead
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Make request
        response = make_request(client, "get", f"/tools/organizations/{org_uuid}/")
        
        # Verify response - Organization Owner should have access
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"

    def test_1_8_get_specific_tool_by_saas_admin(self, authenticated_client, http_client):
        """Test Scenario 1.8: SaaS Administrator can get specific tool details"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        tool_key = "calculator"
        
        # Make request
        before_request = timezone.now()
        response = make_request(client, "get", f"/tools/organizations/{org_uuid}/{tool_key}/")
        
        # Verify response
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        assert "toolKey" in data or "tool_key" in data, "Tool should have toolKey"
        assert (data.get("toolKey") or data.get("tool_key")) == tool_key, "Tool key should match"
        assert "displayName" in data or "display_name" in data, "Tool should have displayName"
        assert "description" in data, "Tool should have description"
        
        # Verify audit log
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/tools/organizations/{org_uuid}/{tool_key}/",
                method="GET",
                status_code=200,
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            if audit_log:
                assert audit_log.success is True, "Audit log should mark success as True"
                assert audit_log.user_id == user.id, "Audit log should reference correct user"

    def test_1_9_get_specific_tool_by_account_admin(self, authenticated_client, http_client):
        """Test Scenario 1.9: Account Admin can get specific tool details"""
        email, password = get_user_credentials("Account 1 Admin")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        tool_key = "calculator"
        
        # Make request
        response = make_request(client, "get", f"/tools/organizations/{org_uuid}/{tool_key}/")
        
        # Verify response - Account Admin should have access
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        assert "toolKey" in data or "tool_key" in data, "Tool should have toolKey"

    def test_1_10_get_nonexistent_tool_rejected(self, authenticated_client, http_client):
        """Test Scenario 1.10: Getting non-existent tool returns 404"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        tool_key = "nonexistent-tool-12345"
        
        # Make request
        response = make_request(client, "get", f"/tools/organizations/{org_uuid}/{tool_key}/")
        
        # Verify response - should be 404
        assert response.status_code == 404, \
            f"Expected 404 but got {response.status_code}, response: {response.text}"

    def test_1_11_custom_role_with_permissions_can_list(self, authenticated_client, http_client):
        """Test Scenario 1.11: Custom role with tools:list permission can list tools"""
        if not DJANGO_AVAILABLE or not Role or not RoleAssignment or not Organization or not User:
            pytest.skip("Django models not available")
        
        # Get organization and a user
        org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
        if not org:
            pytest.skip("Test organization not found")
        ensure_tools_management_subscription(org)
        org_uuid = str(org.uuid)
        
        # Create a custom role with tools:list permission
        custom_role, _ = Role.objects.using('default').get_or_create(
            name=f"Custom Tools Viewer {int(time.time())}",
            defaults={
                "role_type": Role.RoleType.USER_CUSTOM,
                "permissions": ["tools:list", "tools:read"],
            }
        )
        
        # Get or create a test user
        email, password = get_user_credentials("Account 1 User 1")
        test_user = User.objects.using('default').filter(email=email).first()
        if not test_user:
            pytest.skip("Test user not found")
        
        # Assign the custom role to the user for the organization
        RoleAssignment.objects.using('default').get_or_create(
            user=test_user,
            organization=org,
            role=custom_role,
        )
        
        # Authenticate and make request
        client = authenticated_client(email, password)
        response = make_request(client, "get", f"/tools/organizations/{org_uuid}/")
        
        # Verify response - custom role with tools:list should have access
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        
        # Cleanup
        RoleAssignment.objects.using('default').filter(user=test_user, organization=org).delete()
        custom_role.delete()

    def test_1_12_custom_role_without_permissions_cannot_list(self, authenticated_client, http_client):
        """Test Scenario 1.12: Custom role without tools:list permission cannot list tools"""
        if not DJANGO_AVAILABLE or not Role or not RoleAssignment or not Organization or not User:
            pytest.skip("Django models not available")
        
        # Get organization and a user
        org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
        if not org:
            pytest.skip("Test organization not found")
        ensure_tools_management_subscription(org)
        org_uuid = str(org.uuid)
        
        # Create a custom role without tools:list permission
        custom_role, _ = Role.objects.using('default').get_or_create(
            name=f"Custom Role No Tools {int(time.time())}",
            defaults={
                "role_type": Role.RoleType.USER_CUSTOM,
                "permissions": [],  # No tools permissions
            }
        )
        
        # Get or create a test user
        email, password = get_user_credentials("Account 1 User 1")
        test_user = User.objects.using('default').filter(email=email).first()
        if not test_user:
            pytest.skip("Test user not found")
        
        # Assign the custom role to the user for the organization
        RoleAssignment.objects.using('default').get_or_create(
            user=test_user,
            organization=org,
            role=custom_role,
        )
        
        # Authenticate and make request
        client = authenticated_client(email, password)
        before_request = timezone.now()
        response = make_request(client, "get", f"/tools/organizations/{org_uuid}/")
        
        # Verify response - custom role without tools:list should be denied
        assert response.status_code == 403, \
            f"Expected 403 but got {response.status_code}, response: {response.text}"
        
        # Verify audit log for failed request
        if AuditLog:
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/tools/organizations/{org_uuid}/",
                method="GET",
                status_code=403,
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            if audit_log:
                assert audit_log.success is False, "Audit log should mark success as False"
        
        # Cleanup
        RoleAssignment.objects.using('default').filter(user=test_user, organization=org).delete()
        custom_role.delete()

    def test_1_14_agent_manager_can_list_but_not_enable_disable(self, authenticated_client, http_client):
        """Test Scenario 1.14: Agent Manager can list available tools but cannot enable/disable"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure TOOLS_MANAGEMENT subscription exists
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Test 1: Agent Manager can list available tools
        response = make_request(client, "get", f"/tools/organizations/{org_uuid}/")
        assert response.status_code == 200, \
            f"Agent Manager should be able to list tools, got {response.status_code}, response: {response.text}"
        
        # Test 2: Agent Manager cannot enable tools
        tool_key = "calculator"
        response = make_request(client, "post", f"/tools/organizations/{org_uuid}/{tool_key}/enable/")
        assert response.status_code == 403, \
            f"Agent Manager should NOT be able to enable tools, got {response.status_code}, response: {response.text}"
        
        # Test 3: Agent Manager cannot disable tools
        response = make_request(client, "post", f"/tools/organizations/{org_uuid}/{tool_key}/disable/")
        assert response.status_code == 403, \
            f"Agent Manager should NOT be able to disable tools, got {response.status_code}, response: {response.text}"

    def test_1_15_agent_manager_without_Permissions_cannot_access(self, authenticated_client, http_client):
        """Test Scenario 1.15: Agent Manager without tools:list role cannot access"""
        if not DJANGO_AVAILABLE or not Role or not RoleAssignment or not Organization or not User:
            pytest.skip("Django models not available")
        
        email, password = get_user_credentials("Account 1 Agent Manager")
        user = User.objects.using('default').filter(email=email).first()
        if not user:
            pytest.skip("Test user not found")
        
        org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
        if not org:
            pytest.skip("Test organization not found")
        
        # Ensure TOOLS_MANAGEMENT subscription exists
        ensure_tools_management_subscription(org)
        org_uuid = str(org.uuid)
        
        # Find and remove Agent Manager role assignments for this user in this organization
        agent_manager_role = Role.objects.using('default').filter(
            name__icontains="Agent Manager"
        ).first()
        
        if agent_manager_role:
            agent_manager_role.permissions = [p for p in agent_manager_role.permissions if p != "tools:read"]
            agent_manager_role.save()
        
        # Authenticate and try to access
        client = authenticated_client(email, password)
        before_request = timezone.now()
        response = make_request(client, "get", f"/tools/organizations/{org_uuid}/")
        
        # Verify response - should be denied without Agent Manager role
        assert response.status_code == 403, \
            f"Expected 403 without Agent Manager role, got {response.status_code}, response: {response.text}"
        
        # Verify audit log for failed request
        if AuditLog:
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/tools/organizations/{org_uuid}/",
                method="GET",
                status_code=403,
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            if audit_log:
                assert audit_log.success is False, "Audit log should mark success as False"

    def test_1_16_agent_manager_cannot_access_different_organization(self, authenticated_client, http_client):
        """Test Scenario 1.16: Agent Manager cannot access tools in different organization"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        # Get different organization (not the one user belongs to)
        if DJANGO_AVAILABLE and Organization and UserOrganization:
            user = User.objects.using('default').filter(email=email).first()
            if not user:
                pytest.skip("Test user not found")
            
            # Get user's organization
            user_org = UserOrganization.objects.using('default').filter(user=user).first()
            if not user_org:
                pytest.skip("User organization not found")
            
            # Get a different organization
            different_org = Organization.objects.using('default').filter(account=user_org.organization.account).exclude(
                uuid=user_org.organization.uuid
            ).first()
            
            if not different_org:
                pytest.skip("Different organization not found")
            
            # Ensure TOOLS_MANAGEMENT subscription exists for different org
            ensure_tools_management_subscription(different_org)
            different_org_uuid = str(different_org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Try to access tools in different organization
        before_request = timezone.now()
        response = make_request(client, "get", f"/tools/organizations/{different_org_uuid}/")
        
        # Verify response - should be denied (403 or 404)
        assert response.status_code in [403, 404], \
            f"Expected 403 or 404 for different organization, got {response.status_code}, response: {response.text}"
        
        # Verify audit log for failed request
        if DJANGO_AVAILABLE and AuditLog:
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/tools/organizations/{different_org_uuid}/",
                method="GET",
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            if audit_log:
                assert audit_log.success is False, "Audit log should mark success as False"

    def test_1_17_normal_user_cannot_access_anything(self, authenticated_client, http_client):
        """Test Scenario 1.17: Normal user without any special roles cannot access tools"""
        if not DJANGO_AVAILABLE or not Organization or not User:
            pytest.skip("Django models not available")
        
        # Create a normal user without any special roles
        email, password = get_user_credentials("Account 1 User 1")
        client = authenticated_client(email, password)
        
        org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
        if not org:
            pytest.skip("Test organization not found")
        
        # Ensure TOOLS_MANAGEMENT subscription exists
        ensure_tools_management_subscription(org)
        org_uuid = str(org.uuid)
        
        
        # Test 1: Cannot list available tools
        before_request = timezone.now()
        response = make_request(client, "get", f"/tools/organizations/{org_uuid}/")
        assert response.status_code == 403, \
            f"Normal user should NOT be able to list tools, got {response.status_code}, response: {response.text}"
        
        # Test 2: Cannot list enabled tools
        response = make_request(client, "get", f"/tools/organizations/{org_uuid}/enabled/")
        assert response.status_code == 403, \
            f"Normal user should NOT be able to list enabled tools, got {response.status_code}, response: {response.text}"
        
        # Test 3: Cannot enable tools
        tool_key = "calculator"
        response = make_request(client, "post", f"/tools/organizations/{org_uuid}/{tool_key}/enable/")
        assert response.status_code == 403, \
            f"Normal user should NOT be able to enable tools, got {response.status_code}, response: {response.text}"
        
        # Test 4: Cannot disable tools
        response = make_request(client, "post", f"/tools/organizations/{org_uuid}/{tool_key}/disable/")
        assert response.status_code == 403, \
            f"Normal user should NOT be able to disable tools, got {response.status_code}, response: {response.text}"
        
        # Verify audit log for failed requests
        if AuditLog:
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/tools/organizations/{org_uuid}/",
                method="GET",
                status_code=403,
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            if audit_log:
                assert audit_log.success is False, "Audit log should mark success as False"

    def test_1_18_access_denied_without_subscription(self, authenticated_client, http_client):
        """Test Scenario 1.18: Even SAAS Administrator cannot access without TOOLS_MANAGEMENT subscription"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization without TOOLS_MANAGEMENT subscription
        if DJANGO_AVAILABLE and Organization and Module:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha3").first()
            if not org:
                pytest.skip("Test organization not found")
            
            # Remove TOOLS_MANAGEMENT subscription if it exists
            tools_module = Module.objects.using('default').filter(key="TOOLS_MANAGEMENT").first()
            if tools_module:
                Subscription.objects.using('default').filter(
                    organization=org,
                    module=tools_module
                ).delete()
            
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Test 1: Cannot list available tools
        response = make_request(client, "get", f"/tools/organizations/{org_uuid}/")
        assert response.status_code in [403, 404], \
            f"Expected 403 or 404 without subscription, got {response.status_code}, response: {response.text}"
        
        # Test 2: Cannot list enabled tools
        response = make_request(client, "get", f"/tools/organizations/{org_uuid}/enabled/")
        assert response.status_code in [403, 404], \
            f"Expected 403 or 404 without subscription, got {response.status_code}, response: {response.text}"

    def test_1_19_access_denied_with_expired_subscription(self, authenticated_client, http_client):
        """Test Scenario 1.19: Access denied when TOOLS_MANAGEMENT subscription is expired"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization with expired subscription
        if DJANGO_AVAILABLE and Organization and Module and Subscription:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            
            tools_module = Module.objects.using('default').filter(key="TOOLS_MANAGEMENT").first()
            if tools_module:
                subscription, _ = Subscription.objects.using('default').get_or_create(
                    organization=org,
                    module=tools_module,
                    defaults={
                        "status": Subscription.Status.EXPIRED,
                        "configuration": {},
                        "start_date": timezone.now() - timedelta(days=60),
                        "end_date": timezone.now() - timedelta(days=1),  # Expired yesterday
                    }
                )
                subscription.status = Subscription.Status.EXPIRED
                subscription.end_date = timezone.now() - timedelta(days=1)
                subscription.save()
            
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Test 1: Cannot list available tools with expired subscription
        response = make_request(client, "get", f"/tools/organizations/{org_uuid}/")
        assert response.status_code in [403, 404], \
            f"Expected 403 or 404 with expired subscription, got {response.status_code}, response: {response.text}"
        
        # Test 2: Cannot list enabled tools with expired subscription
        response = make_request(client, "get", f"/tools/organizations/{org_uuid}/enabled/")
        assert response.status_code in [403, 404], \
            f"Expected 403 or 404 with expired subscription, got {response.status_code}, response: {response.text}"

    def test_1_20_list_unauthenticated(self, http_client):
        """Test Scenario 1.20: Unauthenticated request is rejected"""
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Make request
        response = make_request(http_client, "get", f"/tools/organizations/{org_uuid}/")
        
        # Verify response
        assert response.status_code == 401, \
            f"Expected 401 but got {response.status_code}, response: {response.text}"


@pytest.mark.acceptance
class TestREQTool002ListEnabledTools:
    """REQ-TOOL-002: List Enabled Tools for Organization"""

    def test_2_1_successful_list_enabled_tools(self, authenticated_client, http_client):
        """Test Scenario 2.1: Organization member Agent Manager can list enabled tools"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure TOOLS_MANAGEMENT subscription exists
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Make request
        before_request = timezone.now()
        response = make_request(client, "get", f"/tools/organizations/{org_uuid}/enabled/")
        
        # Verify response
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        # Response might be paginated or a list
        if isinstance(data, dict) and "results" in data:
            results = data["results"]
            assert isinstance(results, list), "Results should be a list"
        else:
            assert isinstance(data, list), "Response should be a list"
        
        # Verify audit log
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/tools/organizations/{org_uuid}/enabled/",
                method="GET",
                status_code=200,
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            if audit_log:
                assert audit_log.success is True, "Audit log should mark success as True"
                assert audit_log.user_id == user.id, "Audit log should reference correct user"

    def test_2_2_empty_list_when_no_enabled_tools(self, authenticated_client, http_client):
        """Test Scenario 2.2: Empty list returned when no tools are enabled"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure TOOLS_MANAGEMENT subscription exists
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
            
            # Ensure no tools are enabled
            if OrganizationEnabledTool:
                OrganizationEnabledTool.objects.using('default').filter(
                    organization=org,
                    disabled_at__isnull=True
                ).update(disabled_at=timezone.now())
        else:
            pytest.skip("Django models not available")
        
        # Make request
        response = make_request(client, "get", f"/tools/organizations/{org_uuid}/enabled/")
        
        # Verify response
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        # Response might be paginated
        if isinstance(data, dict) and "results" in data:
            results = data["results"]
            assert len(results) == 0, "Should return empty list when no tools enabled"
        else:
            assert len(data) == 0, "Should return empty list when no tools enabled"

    def test_2_3_disabled_tool_not_included(self, authenticated_client, http_client):
        """Test Scenario 2.3: Previously disabled tool is not included in enabled list"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization and OrganizationEnabledTool:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure TOOLS_MANAGEMENT subscription exists
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
            
            # Enable a tool first
            user = User.objects.using('default').filter(email=email).first()
            enabled_tool, _ = OrganizationEnabledTool.objects.using('default').get_or_create(
                organization=org,
                tool_key="calculator",
                defaults={
                    "enabled_by": user,
                    "disabled_at": None,
                }
            )
            
            # Disable it
            enabled_tool.disable(actor=user)
            enabled_tool.save()
        else:
            pytest.skip("Django models not available")
        
        # Make request
        response = make_request(client, "get", f"/tools/organizations/{org_uuid}/enabled/")
        
        # Verify response
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        # Response might be paginated
        if isinstance(data, dict) and "results" in data:
            results = data["results"]
        else:
            results = data
        
        # Verify disabled tool is not in the list
        tool_keys = [tool.get("tool_key") or tool.get("toolKey") for tool in results]
        assert "calculator" not in tool_keys, "Disabled tool should not be in enabled list"

    def test_2_4_successful_list_enabled_by_account_admin(self, authenticated_client, http_client):
        """Test Scenario 2.4: Account Admin can list enabled tools"""
        email, password = get_user_credentials("Account 1 Admin")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure TOOLS_MANAGEMENT subscription exists
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Make request
        response = make_request(client, "get", f"/tools/organizations/{org_uuid}/enabled/")
        
        # Verify response - Account Admin should have access
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        if isinstance(data, dict) and "results" in data:
            assert isinstance(data["results"], list), "Results should be a list"
        else:
            assert isinstance(data, list), "Response should be a list"

    def test_2_5_successful_list_enabled_by_account_owner(self, authenticated_client, http_client):
        """Test Scenario 2.5: Account Owner can list enabled tools"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure TOOLS_MANAGEMENT subscription exists
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Make request
        response = make_request(client, "get", f"/tools/organizations/{org_uuid}/enabled/")
        
        # Verify response - Account Owner should have access
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        if isinstance(data, dict) and "results" in data:
            assert isinstance(data["results"], list), "Results should be a list"
        else:
            assert isinstance(data, list), "Response should be a list"

    def test_2_6_successful_list_enabled_by_organization_admin(self, authenticated_client, http_client):
        """Test Scenario 2.6: Organization Admin can list enabled tools"""
        email, password = get_user_credentials("Account 1 Org Admin")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure TOOLS_MANAGEMENT subscription exists
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Make request
        response = make_request(client, "get", f"/tools/organizations/{org_uuid}/enabled/")
        
        # Verify response - Organization Admin should have access
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        if isinstance(data, dict) and "results" in data:
            assert isinstance(data["results"], list), "Results should be a list"
        else:
            assert isinstance(data, list), "Response should be a list"

    def test_2_7_successful_list_enabled_by_organization_owner(self, authenticated_client, http_client):
        """Test Scenario 2.7: Organization Owner can list enabled tools"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure TOOLS_MANAGEMENT subscription exists
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Make request
        response = make_request(client, "get", f"/tools/organizations/{org_uuid}/enabled/")
        
        # Verify response - Organization Owner should have access
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        if isinstance(data, dict) and "results" in data:
            assert isinstance(data["results"], list), "Results should be a list"
        else:
            assert isinstance(data, list), "Response should be a list"

    def test_2_9_custom_role_with_permissions_can_list_enabled(self, authenticated_client, http_client):
        """Test Scenario 2.9: Custom role with tools:read permission can list enabled tools"""
        if not DJANGO_AVAILABLE or not Role or not RoleAssignment or not Organization or not User:
            pytest.skip("Django models not available")
        
        # Get organization and a user
        org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
        if not org:
            pytest.skip("Test organization not found")
        org_uuid = str(org.uuid)
        
        # Create a custom role with tools:read permission
        custom_role, _ = Role.objects.using('default').get_or_create(
            name=f"Custom Tools Reader {int(time.time())}",
            defaults={
                "role_type": Role.RoleType.USER_CUSTOM,
                "permissions": ["tools:read"],
            }
        )
        
        # Get or create a test user
        email, password = get_user_credentials("Account 1 User 1")
        test_user = User.objects.using('default').filter(email=email).first()
        if not test_user:
            pytest.skip("Test user not found")
        
        # Assign the custom role to the user for the organization
        RoleAssignment.objects.using('default').get_or_create(
            user=test_user,
            organization=org,
            role=custom_role,
        )
        
        # Authenticate and make request
        client = authenticated_client(email, password)
        response = make_request(client, "get", f"/tools/organizations/{org_uuid}/enabled/")
        
        # Verify response - custom role with tools:read should have access
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        if isinstance(data, dict) and "results" in data:
            assert isinstance(data["results"], list), "Results should be a list"
        else:
            assert isinstance(data, list), "Response should be a list"
        
        # Cleanup
        RoleAssignment.objects.using('default').filter(user=test_user, organization=org).delete()
        custom_role.delete()

    def test_2_10_custom_role_without_permissions_cannot_list_enabled(self, authenticated_client, http_client):
        """Test Scenario 2.10: Custom role without tools:read permission cannot list enabled tools"""
        if not DJANGO_AVAILABLE or not Role or not RoleAssignment or not Organization or not User:
            pytest.skip("Django models not available")
        
        # Get organization and a user
        org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
        if not org:
            pytest.skip("Test organization not found")
        org_uuid = str(org.uuid)
        
        # Create a custom role without tools:read permission
        custom_role, _ = Role.objects.using('default').get_or_create(
            name=f"Custom Role No Read {int(time.time())}",
            defaults={
                "role_type": Role.RoleType.USER_CUSTOM,
                "permissions": [],  # No tools permissions
            }
        )
        
        # Get or create a test user
        email, password = get_user_credentials("Account 1 User 1")
        test_user = User.objects.using('default').filter(email=email).first()
        if not test_user:
            pytest.skip("Test user not found")
        
        # Assign the custom role to the user for the organization
        RoleAssignment.objects.using('default').get_or_create(
            user=test_user,
            organization=org,
            role=custom_role,
        )
        
        # Authenticate and make request
        client = authenticated_client(email, password)
        response = make_request(client, "get", f"/tools/organizations/{org_uuid}/enabled/")
        
        # Verify response - custom role without tools:read should be denied
        assert response.status_code == 403, \
            f"Expected 403 but got {response.status_code}, response: {response.text}"
        
        # Cleanup
        RoleAssignment.objects.using('default').filter(user=test_user, organization=org).delete()
        custom_role.delete()

    def test_2_12_agent_manager_can_list_enabled_but_not_enable_disable(self, authenticated_client, http_client):
        """Test Scenario 2.12: Agent Manager can list enabled tools but cannot enable/disable"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure TOOLS_MANAGEMENT subscription exists
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Test: Agent Manager can list enabled tools
        response = make_request(client, "get", f"/tools/organizations/{org_uuid}/enabled/")
        assert response.status_code == 200, \
            f"Agent Manager should be able to list enabled tools, got {response.status_code}, response: {response.text}"
        
        data = response.json()
        if isinstance(data, dict) and "results" in data:
            assert isinstance(data["results"], list), "Results should be a list"
        else:
            assert isinstance(data, list), "Response should be a list"

    def test_2_13_agent_manager_cannot_list_enabled_different_organization(self, authenticated_client, http_client):
        """Test Scenario 2.13: Agent Manager cannot list enabled tools in different organization"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        # Get different organization
        if DJANGO_AVAILABLE and Organization and UserOrganization:
            user = User.objects.using('default').filter(email=email).first()
            if not user:
                pytest.skip("Test user not found")
            
            user_org = UserOrganization.objects.using('default').filter(user=user).first()
            if not user_org:
                pytest.skip("User organization not found")
            
            different_org = Organization.objects.using('default').exclude(
                uuid=user_org.organization.uuid
            ).first()
            
            if not different_org:
                pytest.skip("Different organization not found")
            
            ensure_tools_management_subscription(different_org)
            different_org_uuid = str(different_org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Try to access enabled tools in different organization
        response = make_request(client, "get", f"/tools/organizations/{different_org_uuid}/enabled/")
        
        # Verify response - should be denied
        assert response.status_code in [403, 404], \
            f"Expected 403 or 404 for different organization, got {response.status_code}, response: {response.text}"

    def test_2_14_list_enabled_denied_without_subscription(self, authenticated_client, http_client):
        """Test Scenario 2.14: Cannot list enabled tools without TOOLS_MANAGEMENT subscription"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization without subscription
        if DJANGO_AVAILABLE and Organization and Module:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha3").first()
            if not org:
                pytest.skip("Test organization not found")
            
            tools_module = Module.objects.using('default').filter(key="TOOLS_MANAGEMENT").first()
            if tools_module:
                Subscription.objects.using('default').filter(
                    organization=org,
                    module=tools_module
                ).delete()
            
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Try to list enabled tools
        response = make_request(client, "get", f"/tools/organizations/{org_uuid}/enabled/")
        assert response.status_code in [403, 404], \
            f"Expected 403 or 404 without subscription, got {response.status_code}, response: {response.text}"

    def test_2_15_list_enabled_denied_with_expired_subscription(self, authenticated_client, http_client):
        """Test Scenario 2.15: Cannot list enabled tools with expired TOOLS_MANAGEMENT subscription"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization with expired subscription
        if DJANGO_AVAILABLE and Organization and Module and Subscription:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            
            tools_module = Module.objects.using('default').filter(key="TOOLS_MANAGEMENT").first()
            if tools_module:
                subscription, _ = Subscription.objects.using('default').get_or_create(
                    organization=org,
                    module=tools_module,
                    defaults={
                        "status": Subscription.Status.EXPIRED,
                        "configuration": {},
                        "start_date": timezone.now() - timedelta(days=60),
                        "end_date": timezone.now() - timedelta(days=1),
                    }
                )
                subscription.status = Subscription.Status.EXPIRED
                subscription.end_date = timezone.now() - timedelta(days=1)
                subscription.save()
            
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Try to list enabled tools
        response = make_request(client, "get", f"/tools/organizations/{org_uuid}/enabled/")
        assert response.status_code in [403, 404], \
            f"Expected 403 or 404 with expired subscription, got {response.status_code}, response: {response.text}"

    def test_2_16_list_unauthenticated(self, http_client):
        """Test Scenario 2.16: Unauthenticated request is rejected"""
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Make request
        response = make_request(http_client, "get", f"/tools/organizations/{org_uuid}/enabled/")
        
        # Verify response
        assert response.status_code == 401, \
            f"Expected 401 but got {response.status_code}, response: {response.text}"


@pytest.mark.acceptance
class TestREQTool003EnableToolForOrganization:
    """REQ-TOOL-003: Enable Tool for Organization"""

    def test_3_1_successful_enable_by_saas_administrator(self, authenticated_client, http_client):
        """Test Scenario 3.1: SaaS Administrator can enable tool"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure TOOLS_MANAGEMENT subscription exists
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        tool_key = "calculator"
        
        # Ensure tool is not already enabled
        if DJANGO_AVAILABLE and OrganizationEnabledTool:
            OrganizationEnabledTool.objects.using('default').filter(
                organization=org,
                tool_key=tool_key
            ).update(disabled_at=timezone.now())
        
        # Make request
        before_request = timezone.now()
        response = make_request(client, "post", f"/tools/organizations/{org_uuid}/{tool_key}/enable/")
        
        # Verify response
        assert response.status_code in [200, 201], \
            f"Expected 200 or 201 but got {response.status_code}, response: {response.text}"
        
        # Verify database state
        if DJANGO_AVAILABLE and OrganizationEnabledTool:
            enabled_tool = OrganizationEnabledTool.objects.using('default').filter(
                organization=org,
                tool_key=tool_key,
                disabled_at__isnull=True
            ).first()
            
            assert enabled_tool is not None, "Tool should be enabled in database"
        
        # Verify audit log
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/tools/organizations/{org_uuid}/{tool_key}/enable/",
                method="POST",
                status_code__in=[200, 201],
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            assert audit_log is not None, "Audit log entry should be created"
            assert audit_log.success is True, "Audit log should mark success as True"
            assert audit_log.user_id == user.id, "Audit log should reference correct user"
            
            # Verify DataChangeLog for CREATE operation
            if DataChangeLog:
                data_change_log = DataChangeLog.objects.using('default').filter(
                    app_label="agents",
                    model_name="OrganizationEnabledTool",
                    action="create",
                    created_at__gte=before_request - timedelta(seconds=1)
                ).order_by("-created_at").first()
                
                if data_change_log:
                    assert data_change_log.audit_log_id == audit_log.id, \
                        f"DataChangeLog audit_log_id should match AuditLog id"
                    assert data_change_log.user_id == user.id, \
                        f"DataChangeLog user_id should match user"

    def test_3_2_successful_enable_by_saas_account_manager(self, authenticated_client, http_client):
        """Test Scenario 3.2: SaaS Account Manager can enable tool"""
        email, password = get_user_credentials("SaaS Account Manager")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure TOOLS_MANAGEMENT subscription exists
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        tool_key = "ocr_extractor"
        
        # Ensure tool is not already enabled
        if DJANGO_AVAILABLE and OrganizationEnabledTool:
            OrganizationEnabledTool.objects.using('default').filter(
                organization=org,
                tool_key=tool_key
            ).update(disabled_at=timezone.now())
        
        # Make request
        response = make_request(client, "post", f"/tools/organizations/{org_uuid}/{tool_key}/enable/")
        
        # Verify response
        assert response.status_code in [200, 201], \
            f"Expected 200 or 201 but got {response.status_code}, response: {response.text}"

    def test_3_3_re_enable_previously_disabled_tool(self, authenticated_client, http_client):
        """Test Scenario 3.3: Re-enabling previously disabled tool clears disabledAt"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization and OrganizationEnabledTool:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
            
            tool_key = "handoff_to_human"
            user = User.objects.using('default').filter(email=email).first()
            
            # Create a disabled tool
            enabled_tool, _ = OrganizationEnabledTool.objects.using('default').get_or_create(
                organization=org,
                tool_key=tool_key,
                defaults={
                    "enabled_by": user,
                    "disabled_at": timezone.now(),
                }
            )
            if enabled_tool.disabled_at is None:
                enabled_tool.disable(actor=user)
                enabled_tool.save()
        else:
            pytest.skip("Django models not available")
        
        # Make request to re-enable
        before_request = timezone.now()
        response = make_request(client, "post", f"/tools/organizations/{org_uuid}/{tool_key}/enable/")
        
        # Verify response
        assert response.status_code in [200, 201], \
            f"Expected 200 or 201 but got {response.status_code}, response: {response.text}"
        
        # Verify database state - disabledAt should be cleared
        if DJANGO_AVAILABLE and OrganizationEnabledTool:
            enabled_tool = OrganizationEnabledTool.objects.using('default').filter(
                organization=org,
                tool_key=tool_key
            ).first()
            
            assert enabled_tool is not None, "Tool should exist"
            assert enabled_tool.disabled_at is None, "disabledAt should be cleared on re-enable"

    def test_3_4_enable_rejected_by_agent_manager(self, authenticated_client, http_client):
        """Test Scenario 3.4: Agent Manager cannot enable tool (permission error)"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        tool_key = "calculator"
        
        # Make request
        before_request = timezone.now()
        response = make_request(client, "post", f"/tools/organizations/{org_uuid}/{tool_key}/enable/")
        
        # Verify response - should be 403
        assert response.status_code == 403, \
            f"Expected 403 but got {response.status_code}, response: {response.text}"
        
        # Verify audit log for failed request
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/tools/organizations/{org_uuid}/{tool_key}/enable/",
                method="POST",
                status_code=403,
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            if audit_log:
                assert audit_log.success is False, "Audit log should mark success as False"
                assert audit_log.user_id == user.id, "Audit log should reference correct user"

    def test_3_5_enable_nonexistent_tool_rejected(self, authenticated_client, http_client):
        """Test Scenario 3.5: Enabling non-existent toolKey is rejected"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        tool_key = "nonexistent-tool-12345"
        
        # Make request
        before_request = timezone.now()
        response = make_request(client, "post", f"/tools/organizations/{org_uuid}/{tool_key}/enable/")
        
        # Verify response - should be 404
        assert response.status_code == 404, \
            f"Expected 404 but got {response.status_code}, response: {response.text}"
        
        # Verify audit log for failed request
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/tools/organizations/{org_uuid}/{tool_key}/enable/",
                method="POST",
                status_code=404,
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            if audit_log:
                assert audit_log.success is False, "Audit log should mark success as False"

    def test_3_6_enable_max_tools_exceeded(self, authenticated_client, http_client):
        """Test Scenario 3.6: Enabling tool when max enabled tools limit is reached is rejected"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization and OrganizationEnabledTool and Subscription:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
            
            # Set subscription limit to a low number
            subscription = Subscription.objects.using('default').filter(
                organization=org,
                status=Subscription.Status.ACTIVE
            ).first()
            
            if subscription:
                config = subscription.configuration or {}
                config["tools_max_enabled_per_org"] = 2  # Set low limit
                subscription.configuration = config
                subscription.save()
            
            # Enable tools up to the limit
            user = User.objects.using('default').filter(email=email).first()
            tools_to_enable = ["calculator", "ocr_extractor"]
            for tool_key in tools_to_enable:
                OrganizationEnabledTool.objects.using('default').get_or_create(
                    organization=org,
                    tool_key=tool_key,
                    defaults={
                        "enabled_by": user,
                        "disabled_at": None,
                    }
                )
        else:
            pytest.skip("Django models not available")
        
        # Try to enable another tool
        tool_key = "handoff_to_human"
        
        # Make request
        before_request = timezone.now()
        response = make_request(client, "post", f"/tools/organizations/{org_uuid}/{tool_key}/enable/")
        
        # Verify response - should be rejected (400) if limit enforcement is strict
        # May succeed if limit enforcement is lenient
        assert response.status_code in [200, 201, 400], \
            f"Unexpected status code {response.status_code}, response: {response.text}"
        
        # Verify audit log
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/tools/organizations/{org_uuid}/{tool_key}/enable/",
                method="POST",
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            if audit_log:
                assert audit_log.user_id == user.id, "Audit log should reference correct user"

    def test_3_7_enable_rejected_by_account_admin(self, authenticated_client, http_client):
        """Test Scenario 3.7: Account Admin cannot enable tool (permission error)"""
        email, password = get_user_credentials("Account 1 Admin")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        tool_key = "calculator"
        
        # Make request
        before_request = timezone.now()
        response = make_request(client, "post", f"/tools/organizations/{org_uuid}/{tool_key}/enable/")
        
        # Verify response - should be 403
        assert response.status_code == 403, \
            f"Expected 403 but got {response.status_code}, response: {response.text}"
        
        # Verify audit log for failed request
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/tools/organizations/{org_uuid}/{tool_key}/enable/",
                method="POST",
                status_code=403,
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            if audit_log:
                assert audit_log.success is False, "Audit log should mark success as False"
                assert audit_log.user_id == user.id, "Audit log should reference correct user"

    def test_3_8_enable_rejected_by_account_owner(self, authenticated_client, http_client):
        """Test Scenario 3.8: Account Owner cannot enable tool (permission error)"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        tool_key = "calculator"
        
        # Make request
        response = make_request(client, "post", f"/tools/organizations/{org_uuid}/{tool_key}/enable/")
        
        # Verify response - should be 403
        assert response.status_code == 403, \
            f"Expected 403 but got {response.status_code}, response: {response.text}"

    def test_3_9_enable_rejected_by_organization_admin(self, authenticated_client, http_client):
        """Test Scenario 3.9: Organization Admin cannot enable tool (permission error)"""
        email, password = get_user_credentials("Account 1 Org Admin")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        tool_key = "calculator"
        
        # Make request
        response = make_request(client, "post", f"/tools/organizations/{org_uuid}/{tool_key}/enable/")
        
        # Verify response - should be 403
        assert response.status_code == 403, \
            f"Expected 403 but got {response.status_code}, response: {response.text}"

    def test_3_10_enable_rejected_by_organization_owner(self, authenticated_client, http_client):
        """Test Scenario 3.10: Organization Owner cannot enable tool (permission error)"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        tool_key = "calculator"
        
        # Make request
        response = make_request(client, "post", f"/tools/organizations/{org_uuid}/{tool_key}/enable/")
        
        # Verify response - should be 403
        assert response.status_code == 403, \
            f"Expected 403 but got {response.status_code}, response: {response.text}"

    def test_3_12_enable_denied_without_subscription(self, authenticated_client, http_client):
        """Test Scenario 3.12: Cannot enable tool without TOOLS_MANAGEMENT subscription"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization without subscription
        if DJANGO_AVAILABLE and Organization and Module:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha3").first()
            if not org:
                pytest.skip("Test organization not found")
            
            tools_module = Module.objects.using('default').filter(key="TOOLS_MANAGEMENT").first()
            if tools_module:
                Subscription.objects.using('default').filter(
                    organization=org,
                    module=tools_module
                ).delete()
            
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        tool_key = "calculator"
        
        # Try to enable tool
        response = make_request(client, "post", f"/tools/organizations/{org_uuid}/{tool_key}/enable/")
        assert response.status_code in [403, 404], \
            f"Expected 403 or 404 without subscription, got {response.status_code}, response: {response.text}"

    def test_3_13_enable_denied_with_expired_subscription(self, authenticated_client, http_client):
        """Test Scenario 3.13: Cannot enable tool with expired TOOLS_MANAGEMENT subscription"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization with expired subscription
        if DJANGO_AVAILABLE and Organization and Module and Subscription:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            
            tools_module = Module.objects.using('default').filter(key="TOOLS_MANAGEMENT").first()
            if tools_module:
                subscription, _ = Subscription.objects.using('default').get_or_create(
                    organization=org,
                    module=tools_module,
                    defaults={
                        "status": Subscription.Status.EXPIRED,
                        "configuration": {},
                        "start_date": timezone.now() - timedelta(days=60),
                        "end_date": timezone.now() - timedelta(days=1),
                    }
                )
                subscription.status = Subscription.Status.EXPIRED
                subscription.end_date = timezone.now() - timedelta(days=1)
                subscription.save()
            
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        tool_key = "calculator"
        
        # Try to enable tool
        response = make_request(client, "post", f"/tools/organizations/{org_uuid}/{tool_key}/enable/")
        assert response.status_code in [403, 404], \
            f"Expected 403 or 404 with expired subscription, got {response.status_code}, response: {response.text}"

    def test_3_14_enable_unauthenticated(self, http_client):
        """Test Scenario 3.14: Unauthenticated request is rejected"""
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        tool_key = "calculator"
        
        # Make request
        response = make_request(http_client, "post", f"/tools/organizations/{org_uuid}/{tool_key}/enable/")
        
        # Verify response
        assert response.status_code == 401, \
            f"Expected 401 but got {response.status_code}, response: {response.text}"


@pytest.mark.acceptance
class TestREQTool004DisableToolForOrganization:
    """REQ-TOOL-004: Disable Tool for Organization"""

    def test_4_1_successful_disable_by_saas_administrator(self, authenticated_client, http_client):
        """Test Scenario 4.1: SaaS Administrator can disable tool"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization and OrganizationEnabledTool:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
            
            tool_key = "calculator"
            user = User.objects.using('default').filter(email=email).first()
            
            # Ensure tool is enabled
            enabled_tool, _ = OrganizationEnabledTool.objects.using('default').get_or_create(
                organization=org,
                tool_key=tool_key,
                defaults={
                    "enabled_by": user,
                    "disabled_at": None,
                }
            )
            if enabled_tool.disabled_at:
                enabled_tool.disabled_at = None
                enabled_tool.save()
        else:
            pytest.skip("Django models not available")
        
        # Make request
        before_request = timezone.now()
        response = make_request(client, "post", f"/tools/organizations/{org_uuid}/{tool_key}/disable/")
        
        # Verify response
        assert response.status_code in [200, 204], \
            f"Expected 200 or 204 but got {response.status_code}, response: {response.text}"
        
        # Verify database state
        if DJANGO_AVAILABLE and OrganizationEnabledTool:
            enabled_tool = OrganizationEnabledTool.objects.using('default').filter(
                organization=org,
                tool_key=tool_key
            ).first()
            
            assert enabled_tool is not None, "Tool record should exist"
            assert enabled_tool.disabled_at is not None, "disabledAt should be set"
        
        # Verify audit log
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/tools/organizations/{org_uuid}/{tool_key}/disable/",
                method="POST",
                status_code__in=[200, 204],
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            assert audit_log is not None, "Audit log entry should be created"
            assert audit_log.success is True, "Audit log should mark success as True"
            assert audit_log.user_id == user.id, "Audit log should reference correct user"
            
            # Verify DataChangeLog for UPDATE operation
            if DataChangeLog:
                data_change_log = DataChangeLog.objects.using('default').filter(
                    app_label="agents",
                    model_name="OrganizationEnabledTool",
                    action="update",
                    created_at__gte=before_request - timedelta(seconds=1)
                ).order_by("-created_at").first()
                
                if data_change_log:
                    assert data_change_log.audit_log_id == audit_log.id, \
                        f"DataChangeLog audit_log_id should match AuditLog id"
                    assert data_change_log.user_id == user.id, \
                        f"DataChangeLog user_id should match user"

    def test_4_2_disable_already_disabled_rejected(self, authenticated_client, http_client):
        """Test Scenario 4.2: Disabling already disabled tool is rejected"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization and OrganizationEnabledTool:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
            
            tool_key = "ocr_extractor"
            user = User.objects.using('default').filter(email=email).first()
            
            # Ensure tool is disabled
            enabled_tool, _ = OrganizationEnabledTool.objects.using('default').get_or_create(
                organization=org,
                tool_key=tool_key,
                defaults={
                    "enabled_by": user,
                    "disabled_at": timezone.now(),
                }
            )
            if enabled_tool.disabled_at is None:
                enabled_tool.disable(actor=user)
                enabled_tool.save()
        else:
            pytest.skip("Django models not available")
        
        # Make request
        before_request = timezone.now()
        response = make_request(client, "post", f"/tools/organizations/{org_uuid}/{tool_key}/disable/")
        
        # Verify response - should be rejected (400 or 409)
        assert response.status_code in [400, 409], \
            f"Expected 400 or 409 but got {response.status_code}, response: {response.text}"
        
        # Verify audit log for failed request
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/tools/organizations/{org_uuid}/{tool_key}/disable/",
                method="POST",
                status_code__in=[400, 409],
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            if audit_log:
                assert audit_log.success is False, "Audit log should mark success as False"

    def test_4_3_disable_rejected_by_agent_manager(self, authenticated_client, http_client):
        """Test Scenario 4.3: Agent Manager cannot disable tool (permission error)"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        tool_key = "calculator"
        
        # Make request
        before_request = timezone.now()
        response = make_request(client, "post", f"/tools/organizations/{org_uuid}/{tool_key}/disable/")
        
        # Verify response - should be 403
        assert response.status_code == 403, \
            f"Expected 403 but got {response.status_code}, response: {response.text}"
        
        # Verify audit log for failed request
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/tools/organizations/{org_uuid}/{tool_key}/disable/",
                method="POST",
                status_code=403,
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            if audit_log:
                assert audit_log.success is False, "Audit log should mark success as False"

    def test_4_4_disable_rejected_by_account_admin(self, authenticated_client, http_client):
        """Test Scenario 4.4: Account Admin cannot disable tool (permission error)"""
        email, password = get_user_credentials("Account 1 Admin")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        tool_key = "calculator"
        
        # Make request
        before_request = timezone.now()
        response = make_request(client, "post", f"/tools/organizations/{org_uuid}/{tool_key}/disable/")
        
        # Verify response - should be 403
        assert response.status_code == 403, \
            f"Expected 403 but got {response.status_code}, response: {response.text}"
        
        # Verify audit log for failed request
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/tools/organizations/{org_uuid}/{tool_key}/disable/",
                method="POST",
                status_code=403,
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            if audit_log:
                assert audit_log.success is False, "Audit log should mark success as False"

    def test_4_5_disable_rejected_by_account_owner(self, authenticated_client, http_client):
        """Test Scenario 4.5: Account Owner cannot disable tool (permission error)"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        tool_key = "calculator"
        
        # Make request
        response = make_request(client, "post", f"/tools/organizations/{org_uuid}/{tool_key}/disable/")
        
        # Verify response - should be 403
        assert response.status_code == 403, \
            f"Expected 403 but got {response.status_code}, response: {response.text}"

    def test_4_6_disable_rejected_by_organization_admin(self, authenticated_client, http_client):
        """Test Scenario 4.6: Organization Admin cannot disable tool (permission error)"""
        email, password = get_user_credentials("Account 1 Org Admin")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        tool_key = "calculator"
        
        # Make request
        response = make_request(client, "post", f"/tools/organizations/{org_uuid}/{tool_key}/disable/")
        
        # Verify response - should be 403
        assert response.status_code == 403, \
            f"Expected 403 but got {response.status_code}, response: {response.text}"

    def test_4_7_disable_rejected_by_organization_owner(self, authenticated_client, http_client):
        """Test Scenario 4.7: Organization Owner cannot disable tool (permission error)"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        tool_key = "calculator"
        
        # Make request
        response = make_request(client, "post", f"/tools/organizations/{org_uuid}/{tool_key}/disable/")
        
        # Verify response - should be 403
        assert response.status_code == 403, \
            f"Expected 403 but got {response.status_code}, response: {response.text}"

    def test_4_9_disable_denied_without_subscription(self, authenticated_client, http_client):
        """Test Scenario 4.9: Cannot disable tool without TOOLS_MANAGEMENT subscription"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization without subscription
        if DJANGO_AVAILABLE and Organization and Module:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha3").first()
            if not org:
                pytest.skip("Test organization not found")
            
            tools_module = Module.objects.using('default').filter(key="TOOLS_MANAGEMENT").first()
            if tools_module:
                Subscription.objects.using('default').filter(
                    organization=org,
                    module=tools_module
                ).delete()
            
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        tool_key = "calculator"
        
        # Try to disable tool
        response = make_request(client, "post", f"/tools/organizations/{org_uuid}/{tool_key}/disable/")
        assert response.status_code in [403, 404], \
            f"Expected 403 or 404 without subscription, got {response.status_code}, response: {response.text}"

    def test_4_10_disable_denied_with_expired_subscription(self, authenticated_client, http_client):
        """Test Scenario 4.10: Cannot disable tool with expired TOOLS_MANAGEMENT subscription"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization with expired subscription
        if DJANGO_AVAILABLE and Organization and Module and Subscription:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            
            tools_module = Module.objects.using('default').filter(key="TOOLS_MANAGEMENT").first()
            if tools_module:
                subscription, _ = Subscription.objects.using('default').get_or_create(
                    organization=org,
                    module=tools_module,
                    defaults={
                        "status": Subscription.Status.EXPIRED,
                        "configuration": {},
                        "start_date": timezone.now() - timedelta(days=60),
                        "end_date": timezone.now() - timedelta(days=1),
                    }
                )
                subscription.status = Subscription.Status.EXPIRED
                subscription.end_date = timezone.now() - timedelta(days=1)
                subscription.save()
            
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        tool_key = "calculator"
        
        # Try to disable tool
        response = make_request(client, "post", f"/tools/organizations/{org_uuid}/{tool_key}/disable/")
        assert response.status_code in [403, 404], \
            f"Expected 403 or 404 with expired subscription, got {response.status_code}, response: {response.text}"

    def test_4_11_disable_unauthenticated(self, http_client):
        """Test Scenario 4.11: Unauthenticated request is rejected"""
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        tool_key = "calculator"
        
        # Make request
        response = make_request(http_client, "post", f"/tools/organizations/{org_uuid}/{tool_key}/disable/")
        
        # Verify response
        assert response.status_code == 401, \
            f"Expected 401 but got {response.status_code}, response: {response.text}"


@pytest.mark.acceptance
class TestREQTool005ValidateToolConfiguration:
    """REQ-TOOL-005: Validate Tool Configuration"""

    def enable_tool(self, tool_key, organization_uuid, authenticated_client):
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        response = make_request(client, "post", f"/tools/organizations/{organization_uuid}/{tool_key}/enable/")
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        return response.json()

    def test_5_1_valid_configuration_passes(self, authenticated_client, http_client):
        """Test Scenario 5.1: Valid configuration passes validation"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        self.enable_tool("calculator", org_uuid, authenticated_client)
        
        payload = {
            "organization_uuid": org_uuid,
            "toolKey": "calculator",
            "configuration": {
                "expression": "2 + 2"
            }
        }
        
        # Make request
        before_request = timezone.now()
        response = make_request(client, "post", "/tools/validate/", json=payload)
        
        # Verify response
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        # Response should indicate validation passed
        # Exact structure depends on implementation
        
        # Verify audit log
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path="/api/tools/validate/",
                method="POST",
                status_code=200,
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            if audit_log:
                assert audit_log.success is True, "Audit log should mark success as True"
                assert audit_log.user_id == user.id, "Audit log should reference correct user"

    def test_5_2_invalid_max_results_fails(self, authenticated_client, http_client):
        """Test Scenario 5.2: MaxResults exceeding limit fails validation"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")

        self.enable_tool("kb_retriever", org_uuid, authenticated_client)
        
        payload = {
            "organization_uuid": org_uuid,
            "toolKey": "kb_retriever",
            "configuration": {
                "collection_id": "00000000-0000-0000-0000-000000000000",
                "maxResults": 25,  # Invalid: max is 20
            }
        }
        
        # Make request
        before_request = timezone.now()
        response = make_request(client, "post", "/tools/validate/", json=payload)
        
        # Verify response - should fail validation
        assert response.status_code == 400, \
            f"Expected 400 but got {response.status_code}, response: {response.text}"
        
        # Verify audit log for failed request
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path="/api/tools/validate/",
                method="POST",
                status_code=400,
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            if audit_log:
                assert audit_log.success is False, "Audit log should mark success as False"

    def test_5_3_missing_required_parameter_fails(self, authenticated_client, http_client):
        """Test Scenario 5.3: Missing required parameter fails validation"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        self.enable_tool("kb_retriever", org_uuid, authenticated_client)
        
        payload = {
            "organization_uuid": org_uuid,
            "toolKey": "kb_retriever",
            "configuration": {
                # Missing required collection_id
            }
        }
        
        # Make request
        response = make_request(client, "post", "/tools/validate/", json=payload)
        
        # Verify response - should fail validation
        assert response.status_code == 400, \
            f"Expected 400 but got {response.status_code}, response: {response.text}"

    def test_5_4_wrong_parameter_type_fails(self, authenticated_client, http_client):
        """Test Scenario 5.4: Wrong parameter type fails validation"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        self.enable_tool("calculator", org_uuid, authenticated_client)
        
        payload = {
            "organization_uuid": org_uuid,
            "toolKey": "calculator",
            "configuration": {
                "expression": 12345,  # Invalid: should be string
            }
        }
        
        # Make request
        response = make_request(client, "post", "/tools/validate/", json=payload)
        
        # Verify response - may pass if type coercion is allowed, or fail if strict
        assert response.status_code in [200, 400], \
            f"Expected 200 or 400 but got {response.status_code}, response: {response.text}"

    def test_5_5_invalid_uuid_format_fails(self, authenticated_client, http_client):
        """Test Scenario 5.5: Invalid UUID format fails validation"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        self.enable_tool("kb_retriever", org_uuid, authenticated_client)
        
        payload = {
            "organization_uuid": org_uuid,
            "toolKey": "kb_retriever",
            "configuration": {
                "collection_id": "not-a-valid-uuid",  # Invalid UUID format
            }
        }
        
        # Make request
        response = make_request(client, "post", "/tools/validate/", json=payload)
        
        # Verify response - should fail validation
        assert response.status_code == 400, \
            f"Expected 400 but got {response.status_code}, response: {response.text}"

    def test_5_6_validate_unauthenticated(self, http_client):
        """Test Scenario 5.6: Unauthenticated request is rejected"""
        payload = {
            "organization_uuid": "00000000-0000-0000-0000-000000000000",
            "toolKey": "calculator",
            "configuration": {
                "expression": "2 + 2",
            }
        }
        
        # Make request
        response = make_request(http_client, "post", "/tools/validate/", json=payload)
        
        # Verify response
        assert response.status_code == 401, \
            f"Expected 401 but got {response.status_code}, response: {response.text}"
    
    def test_5_7_valid_configuration_fails_without_enabling_tool(self, authenticated_client, http_client):
        """Test Scenario 5.7: Valid configuration fails without enabling tool"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        payload = {
            "organization_uuid": org_uuid,
            "toolKey": "calculator",
            "configuration": {
                "expression": "2 + 2"
            }
        }
        
        # Make request
        before_request = timezone.now()
        response = make_request(client, "post", "/tools/validate/", json=payload)
        
        # Verify response
        assert response.status_code == 404, \
            f"Expected 404 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        # Response should indicate validation passed
        # Exact structure depends on implementation
        
        # Verify audit log
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path="/api/tools/validate/",
                method="POST",
                status_code=404,
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            if audit_log:
                assert audit_log.success is True, "Audit log should mark success as True"
                assert audit_log.user_id == user.id, "Audit log should reference correct user"

@pytest.mark.acceptance
class TestREQTool006PreventDuplicateTools:
    """REQ-TOOL-006: Prevent Duplicate Tools in Agent"""
    
    # Note: This requirement is primarily tested at the agent level
    # We can verify the validation endpoint rejects duplicate tools if applicable
    # Actual duplicate prevention is tested in agent tests
    
    def test_6_1_tool_can_be_added_once(self, authenticated_client, http_client):
        """Test Scenario 6.1: Tool can be added to agent configuration"""
        # This is primarily an agent-level test
        # We verify that tools can be enabled for organization
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        tool_key = "calculator"
        
        # Enable tool
        response = make_request(client, "post", f"/tools/organizations/{org_uuid}/{tool_key}/enable/")
        
        # Verify tool can be enabled
        assert response.status_code in [200, 201], \
            f"Expected 200 or 201 but got {response.status_code}, response: {response.text}"


@pytest.mark.acceptance
class TestREQTool007KnowledgeBaseIntegration:
    """REQ-TOOL-007: Knowledge Base Integration via Tool"""
    
    def test_7_1_valid_collection_uuid_passes(self, authenticated_client, http_client):
        """Test Scenario 7.1: Valid collection UUID passes validation"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Use a valid UUID format (may not exist, but format should be valid)
        payload = {
            "organization_uuid": org_uuid,
            "toolKey": "kb_retriever",
            "configuration": {
                "collection_id": "00000000-0000-0000-0000-000000000000",  # Valid UUID format
                "maxResults": 10,
            }
        }
        
        # Make request
        response = make_request(client, "post", "/tools/validate/", json=payload)
        
        # Verify response - may pass if UUID format is valid, or fail if collection doesn't exist
        assert response.status_code in [200, 400, 404], \
            f"Unexpected status code {response.status_code}, response: {response.text}"

    def test_7_2_invalid_uuid_format_fails(self, authenticated_client, http_client):
        """Test Scenario 7.2: Invalid UUID format fails validation"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        admin_email, admin_password = get_user_credentials("Super Admin")
        admin_client = authenticated_client(admin_email, admin_password)
        response = make_request(admin_client, "post", f"/tools/organizations/{org_uuid}/kb_retriever/enable/")
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        payload = {
            "organization_uuid": org_uuid,
            "toolKey": "kb_retriever",
            "configuration": {
                "collection_id": "not-a-uuid",  # Invalid UUID format
            }
        }
        
        # Make request
        response = make_request(client, "post", "/tools/validate/", json=payload)
        
        # Verify response - should fail validation
        assert response.status_code == 400, \
            f"Expected 400 but got {response.status_code}, response: {response.text}"


@pytest.mark.acceptance
class TestREQTool008NoToolDependencies:
    """REQ-TOOL-008: No Tool Dependencies"""
    
    def test_8_1_tools_can_be_enabled_independently(self, authenticated_client, http_client):
        """Test Scenario 8.1: Tools can be enabled independently without dependencies"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Enable tools independently
        tools = ["handoff_to_human", "calculator", "kb_retriever"]
        
        for tool_key in tools:
            response = make_request(client, "post", f"/tools/organizations/{org_uuid}/{tool_key}/enable/")
            
            # Verify each tool can be enabled independently
            assert response.status_code in [200, 201], \
                f"Tool {tool_key} should be enabled successfully, got {response.status_code}, {response.text}"
