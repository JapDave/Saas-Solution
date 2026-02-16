"""
Acceptance tests for Agents Management API endpoints.

Tests cover all requirements from REQ-AGENTS-001 through REQ-AGENTS-010.
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
    from apps.users.models import User, UserOrganization
    from apps.accounts.models import Account
    from apps.organizations.models import Organization
    from apps.common.models import AuditLog, DataChangeLog
    from apps.agents.models import Agent, AgentVersion, OrganizationEnabledLLM, OrganizationEnabledTool
    from apps.llms.models import LLMDefinition
    from apps.subscriptions.models import Subscription
    from apps.roles.models import Role, RoleAssignment
    from apps.products.models import Module
    DJANGO_AVAILABLE = True
except ImportError:
    DJANGO_AVAILABLE = False
    User = None
    UserOrganization = None
    Account = None
    Organization = None
    AuditLog = None
    DataChangeLog = None
    Agent = None
    AgentVersion = None
    OrganizationEnabledLLM = None
    OrganizationEnabledTool = None
    Subscription = None
    Role = None
    RoleAssignment = None
    Module = None
    LLMDefinition = None
    timezone = None
    timedelta = None


def ensure_agents_management_subscription(org):
    """Helper function to ensure organization has AGENTS_MANAGEMENT subscription"""
    if not DJANGO_AVAILABLE or not Module or not Subscription:
        return None
    
    agents_module = Module.objects.using('default').filter(key="AGENTS_MANAGEMENT").first()
    if not agents_module:
        return None
    
    subscription, _ = Subscription.objects.using('default').get_or_create(
        organization=org,
        module=agents_module,
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


def ensure_llm_management_subscription(org):
    """Helper function to ensure organization has LLM_MANAGEMENT subscription"""
    if not DJANGO_AVAILABLE or not Module or not Subscription:
        return None
    
    llm_module = Module.objects.using('default').filter(key="LLM_MANAGEMENT").first()
    if not llm_module:
        return None
    
    subscription, _ = Subscription.objects.using('default').get_or_create(
        organization=org,
        module=llm_module,
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


def enable_llm_for_org(org, model_key, actor):
    """Helper function to enable an LLM for an organization"""
    if not DJANGO_AVAILABLE or not OrganizationEnabledLLM or not LLMDefinition:
        return None
    
    llm_def = LLMDefinition.objects.using('default').filter(model_key=model_key, is_active=True).first()
    if not llm_def:
        return None
    
    enabled_llm, _ = OrganizationEnabledLLM.objects.using('default').get_or_create(
        organization=org,
        model_key=model_key,
        defaults={
            "model_provider": llm_def.model_provider,
            "display_name": llm_def.display_name,
            "enabled_by": actor,
            "disabled_at": None,
        }
    )
    if enabled_llm.disabled_at:
        enabled_llm.disabled_at = None
        enabled_llm.enabled_by = actor
        enabled_llm.save()
    
    return enabled_llm


def enable_tool_for_org(org, tool_key, actor):
    """Helper function to enable a tool for an organization"""
    if not DJANGO_AVAILABLE or not OrganizationEnabledTool:
        return None
    
    # Get tool definition from static file (simplified - in real implementation would read from tools-list.json)
    tool_display_names = {
        "kb_retriever": "Knowledge Base Retriever",
        "calculator": "Calculator",
        "ocr_extractor": "OCR Extractor",
        "handoff_to_human": "Handoff to Human",
        "image_analyzer": "Image Analyzer",
    }
    
    enabled_tool, _ = OrganizationEnabledTool.objects.using('default').get_or_create(
        organization=org,
        tool_key=tool_key,
        defaults={
            "display_name": tool_display_names.get(tool_key, tool_key),
            "category": "knowledge" if tool_key == "kb_retriever" else "other",
            "enabled_by": actor,
            "disabled_at": None,
        }
    )
    if enabled_tool.disabled_at:
        enabled_tool.disabled_at = None
        enabled_tool.enabled_by = actor
        enabled_tool.save()
    
    return enabled_tool


@pytest.mark.acceptance
class TestREQAgents001CreateAndManageAgents:
    """REQ-AGENTS-001: Create and Manage Agents"""

    def test_1_1_successful_creation_by_agent_manager(self, authenticated_client, http_client):
        """Test Scenario 1.1: Agent Manager can create agent with unique name"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure AGENTS_MANAGEMENT subscription exists
            ensure_agents_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        payload = {
            "organization": org_uuid,
            "name": f"Test Agent {int(time.time())}",
            "description": "Test agent description"
        }
        
        # Make request
        before_request = timezone.now()
        response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=payload)
        
        # Verify response
        assert response.status_code == 201, \
            f"Expected 201 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        assert "uuid" in data or "id" in data, "Response should contain agent identifier"
        assert data.get("name") == payload["name"], "Name should match"
        assert data.get("state") == "draft", "Agent should be created in Draft state"
        agent_uuid = data.get("uuid") or data.get("id")
        
        # Verify database state
        if DJANGO_AVAILABLE and Agent:
            agent = Agent.objects.using('default').filter(uuid=agent_uuid).first()
            assert agent is not None, "Agent should exist in database"
            assert agent.state == Agent.AgentState.DRAFT, "Agent should be in Draft state"
            assert agent.name == payload["name"], "Agent name should match"
        
        # Verify audit log
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/agents/organizations/{org_uuid}/",
                method="POST",
                status_code=201,
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            assert audit_log is not None, "Audit log entry should be created"
            assert audit_log.success is True, "Audit log should mark success as True"
            assert audit_log.user_id == user.id, "Audit log should reference correct user"
            
            # Verify DataChangeLog for CREATE operation
            if DataChangeLog:
                data_change_log = DataChangeLog.objects.using('default').filter(
                    app_label="agents",
                    model_name="Agent",
                    action="create",
                    object_id=agent_uuid,
                    created_at__gte=before_request - timedelta(seconds=1)
                ).order_by("-created_at").first()
                
                assert data_change_log is not None, "DataChangeLog entry should be created for CREATE"
                assert data_change_log.audit_log_id == audit_log.id, \
                    f"DataChangeLog audit_log_id should match AuditLog id: {data_change_log.audit_log_id} != {audit_log.id}"
                assert data_change_log.user_id == user.id, \
                    f"DataChangeLog user_id should match user: {data_change_log.user_id} != {user.id}"
                assert data_change_log.trace_id is not None, "DataChangeLog trace_id should not be null"
                assert data_change_log.span_id is not None, "DataChangeLog span_id should not be null"
                
                # Verify changed_fields
                changed_fields = data_change_log.changed_fields
                assert isinstance(changed_fields, dict), "changed_fields should be a dictionary"
                assert "name" in changed_fields, "changed_fields should contain 'name'"
                assert changed_fields["name"]["new"] == payload["name"], "Name should match payload"
                assert changed_fields["name"]["old"] is None, "Old value should be None for CREATE"
                
                # Verify changed_fields_summary
                assert data_change_log.changed_fields_summary is not None, \
                    "changed_fields_summary should not be null"
                assert "name" in data_change_log.changed_fields_summary, \
                    "changed_fields_summary should contain 'name'"

    def test_1_2_successful_creation_by_saas_administrator(self, authenticated_client, http_client):
        """Test Scenario 1.2: SaaS Administrator can create agent"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        payload = {
            "organization": org_uuid,
            "name": f"Test Agent SAAS {int(time.time())}",
            "description": "Test agent created by SAAS Admin"
        }
        
        response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=payload)
        assert response.status_code == 201, \
            f"Expected 201 but got {response.status_code}, response: {response.text}"

    def test_1_3_successful_creation_by_saas_account_manager(self, authenticated_client, http_client):
        """Test Scenario 1.3: SaaS Account Manager can create agent"""
        email, password = get_user_credentials("SaaS Account Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        payload = {
            "organization": org_uuid,
            "name": f"Test Agent SAM {int(time.time())}",
            "description": "Test agent created by SaaS Account Manager"
        }
        
        response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=payload)
        assert response.status_code == 201, \
            f"Expected 201 but got {response.status_code}, response: {response.text}"

    def test_1_4_successful_creation_by_account_owner(self, authenticated_client, http_client):
        """Test Scenario 1.4: Account Owner can create agent"""
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha2").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        payload = {
            "organization": org_uuid,
            "name": f"Test Agent Owner {int(time.time())}",
            "description": "Test agent created by Account Owner"
        }
        
        response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=payload)
        assert response.status_code == 201, \
            f"Expected 201 but got {response.status_code}, response: {response.text}"

    def test_1_5_successful_creation_by_account_admin(self, authenticated_client, http_client):
        """Test Scenario 1.5: Account Admin can create agent"""
        email, password = get_user_credentials("Account 1 Admin")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        payload = {
            "organization": org_uuid,
            "name": f"Test Agent Admin {int(time.time())}",
            "description": "Test agent created by Account Admin"
        }
        
        response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=payload)
        assert response.status_code == 201, \
            f"Expected 201 but got {response.status_code}, response: {response.text}"

    def test_1_6_successful_creation_by_org_admin(self, authenticated_client, http_client):
        """Test Scenario 1.6: Organization Admin can create agent"""
        email, password = get_user_credentials("Account 1 Org Admin")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        payload = {
            "organization": org_uuid,
            "name": f"Test Agent OrgAdmin {int(time.time())}",
            "description": "Test agent created by Org Admin"
        }
        
        response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=payload)
        assert response.status_code == 201, \
            f"Expected 201 but got {response.status_code}, response: {response.text}"

    def test_1_7_creation_rejected_without_permission(self, authenticated_client, http_client):
        """Test Scenario 1.7: User without agents:create permission cannot create agent"""
        email, password = get_user_credentials("Account 1 User 1")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        payload = {
            "organization": org_uuid,
            "name": f"Test Agent NoPerm {int(time.time())}",
            "description": "Test agent"
        }
        
        before_request = timezone.now()
        response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=payload)
        
        assert response.status_code == 403, \
            f"Expected 403 but got {response.status_code}, response: {response.text}"
        
        # Verify audit log for failed request
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/agents/organizations/{org_uuid}/",
                method="POST",
                status_code=403,
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            if audit_log:
                assert audit_log.success is False, "Audit log should mark success as False"
                assert audit_log.user_id == user.id, "Audit log should reference correct user"

    def test_1_8_creation_rejected_without_subscription(self, authenticated_client, http_client):
        """Test Scenario 1.8: Organization without AGENTS_MANAGEMENT subscription cannot create agent"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization and Module:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha3").first()
            if not org:
                pytest.skip("Test organization not found")
            
            # Remove AGENTS_MANAGEMENT subscription if it exists
            agents_module = Module.objects.using('default').filter(key="AGENTS_MANAGEMENT").first()
            if agents_module:
                Subscription.objects.using('default').filter(
                    organization=org,
                    module=agents_module
                ).delete()
            
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        payload = {
            "organization": org_uuid,
            "name": f"Test Agent NoSub {int(time.time())}",
            "description": "Test agent"
        }
        
        response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=payload)
        
        assert response.status_code in [403, 404], \
            f"Expected 403 or 404 without subscription but got {response.status_code}, response: {response.text}"
        
        if response.status_code == 403:
            data = response.json()
            assert data.get("code") == "SUBSCRIPTION_REQUIRED" or "subscription" in str(data).lower(), \
                "Error code should indicate subscription required"

    def test_1_9_creation_rejected_duplicate_name(self, authenticated_client, http_client):
        """Test Scenario 1.9: Creating agent with duplicate name is rejected"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        agent_name = f"Duplicate Test Agent {int(time.time())}"
        payload = {
            "organization": org_uuid,
            "name": agent_name,
            "description": "First agent"
        }
        
        # Create first agent
        response1 = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=payload)
        assert response1.status_code == 201, "First agent should be created successfully"
        
        # Try to create duplicate
        before_request = timezone.now()
        response2 = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=payload)
        
        assert response2.status_code in [400, 409], \
            f"Expected 400 or 409 but got {response2.status_code}, response: {response2.text}"
        
        data = response2.json()
        assert "name" in str(data).lower() or "unique" in str(data).lower() or data.get("code") == "AGENT_NAME_NOT_UNIQUE", \
            "Error should indicate duplicate name"

    def test_1_10_creation_rejected_different_organization(self, authenticated_client, http_client):
        """Test Scenario 1.10: User cannot create agent for different organization"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            # Get organization user doesn't have access to
            org = Organization.objects.using('default').filter(name="Test Organization Beta1").first()
            if not org:
                pytest.skip("Test organization not found")
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        payload = {
            "organization": org_uuid,
            "name": f"Test Agent WrongOrg {int(time.time())}",
            "description": "Test agent"
        }
        
        response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=payload)
        
        assert response.status_code == 403, \
            f"Expected 403 but got {response.status_code}, response: {response.text}"

    def test_1_11_creation_unauthenticated(self, http_client):
        """Test Scenario 1.11: Unauthenticated request is rejected"""
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        payload = {
            "organization": org_uuid,
            "name": f"Test Agent Unauth {int(time.time())}",
            "description": "Test agent"
        }
        
        response = make_request(http_client, "post", f"/agents/organizations/{org_uuid}/", json=payload)
        
        assert response.status_code == 401, \
            f"Expected 401 but got {response.status_code}, response: {response.text}"

    def test_1_12_update_agent_description(self, authenticated_client, http_client):
        """Test Scenario 1.12: Update agent description updates updatedAt and updatedBy"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Create agent first
        create_payload = {
            "organization": org_uuid,
            "name": f"Update Test Agent {int(time.time())}",
            "description": "Original description"
        }
        create_response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=create_payload)
        assert create_response.status_code == 201
        agent_uuid = create_response.json().get("uuid") or create_response.json().get("id")
        
        # Update description
        update_payload = {
            "description": "Updated description"
        }
        
        before_request = timezone.now()
        response = make_request(client, "patch", f"/agents/organizations/{org_uuid}/{agent_uuid}/", json=update_payload)
        
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        assert data.get("description") == "Updated description", "Description should be updated"
        
        # Verify database state
        if DJANGO_AVAILABLE and Agent:
            agent = Agent.objects.using('default').filter(uuid=agent_uuid).first()
            assert agent is not None, "Agent should exist"
            assert agent.description == "Updated description", "Description should be updated in database"
            assert agent.updated_at >= before_request, "updatedAt should be updated"
            assert agent.updated_by.email == email, "updatedBy should be set"
        
        # Verify audit log
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/agents/organizations/{org_uuid}/{agent_uuid}/",
                method="PATCH",
                status_code=200,
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            assert audit_log is not None, "Audit log entry should be created"
            assert audit_log.success is True, "Audit log should mark success as True"
            assert audit_log.user_id == user.id, "Audit log should reference correct user"
            
            # Verify DataChangeLog for UPDATE operation
            if DataChangeLog:
                data_change_log = DataChangeLog.objects.using('default').filter(
                    app_label="agents",
                    model_name="Agent",
                    action="update",
                    object_id=agent_uuid,
                    created_at__gte=before_request - timedelta(seconds=1)
                ).order_by("-created_at").first()
                
                assert data_change_log is not None, "DataChangeLog entry should be created for UPDATE"
                assert data_change_log.audit_log_id == audit_log.id, \
                    f"DataChangeLog audit_log_id should match AuditLog id"
                assert data_change_log.user_id == user.id, \
                    f"DataChangeLog user_id should match user"
                
                # Verify changed_fields
                changed_fields = data_change_log.changed_fields
                assert "description" in changed_fields, "changed_fields should contain 'description'"
                assert changed_fields["description"]["old"] == "Original description", \
                    "Old description should match original"
                assert changed_fields["description"]["new"] == "Updated description", \
                    "New description should match updated value"

    def test_1_13_archive_active_agent(self, authenticated_client, http_client):
        """Test Scenario 1.13: Archive Active agent changes state to Archived"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Create and activate agent
        create_payload = {
            "organization": org_uuid,
            "name": f"Archive Test Agent {int(time.time())}",
            "description": "Test agent"
        }
        create_response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=create_payload)
        assert create_response.status_code == 201
        agent_uuid = create_response.json().get("uuid") or create_response.json().get("id")
        
        # Activate agent
        activate_response = make_request(client, "post", f"/agents/organizations/{org_uuid}/{agent_uuid}/activate/")
        assert activate_response.status_code == 200
        
        # Archive agent
        before_request = timezone.now()
        response = make_request(client, "post", f"/agents/organizations/{org_uuid}/{agent_uuid}/archive/")
        
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        assert data.get("state") == "archived", "Agent state should be archived"
        
        # Verify database state
        if DJANGO_AVAILABLE and Agent:
            agent = Agent.objects.using('default').filter(uuid=agent_uuid).first()
            assert agent.state == Agent.AgentState.ARCHIVED, "Agent should be archived in database"

    def test_1_14_restore_archived_agent(self, authenticated_client, http_client):
        """Test Scenario 1.14: Restore archived agent changes state to Active"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Create, activate, and archive agent
        create_payload = {
            "organization": org_uuid,
            "name": f"Restore Test Agent {int(time.time())}",
            "description": "Test agent"
        }
        create_response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=create_payload)
        assert create_response.status_code == 201
        agent_uuid = create_response.json().get("uuid") or create_response.json().get("id")
        
        # Activate and archive
        make_request(client, "post", f"/agents/organizations/{org_uuid}/{agent_uuid}/activate/")
        make_request(client, "post", f"/agents/organizations/{org_uuid}/{agent_uuid}/archive/")
        
        # Restore agent
        before_request = timezone.now()
        response = make_request(client, "post", f"/agents/organizations/{org_uuid}/{agent_uuid}/restore/")
        
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        assert data.get("state") == "active", "Agent state should be active after restore"
        
        # Verify database state
        if DJANGO_AVAILABLE and Agent:
            agent = Agent.objects.using('default').filter(uuid=agent_uuid).first()
            assert agent.state == Agent.AgentState.ACTIVE, "Agent should be active in database"
            assert agent.deleted_at is None, "deletedAt should be cleared"

    def test_1_15_delete_agent_soft_delete(self, authenticated_client, http_client):
        """Test Scenario 1.15: Delete agent performs soft delete"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Create agent
        create_payload = {
            "organization": org_uuid,
            "name": f"Delete Test Agent {int(time.time())}",
            "description": "Test agent"
        }
        create_response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=create_payload)
        assert create_response.status_code == 201
        agent_uuid = create_response.json().get("uuid") or create_response.json().get("id")
        
        # Delete agent
        before_request = timezone.now()
        response = make_request(client, "delete", f"/agents/organizations/{org_uuid}/{agent_uuid}/")
        
        assert response.status_code == 204, \
            f"Expected 204 but got {response.status_code}, response: {response.text}"
        
        # Verify database state - soft delete
        if DJANGO_AVAILABLE and Agent:
            agent = Agent.objects.using('default').all_objects.filter(uuid=agent_uuid).first()
            assert agent is not None, "Agent should still exist (soft delete)"
            assert agent.deleted_at is not None, "deletedAt should be set"
            assert agent.state == Agent.AgentState.DELETED, "Agent state should be DELETED"
            
            # Verify agent is not in default queryset
            assert not Agent.objects.using('default').filter(uuid=agent_uuid).exists(), \
                "Agent should not appear in default queryset"
        
        # Verify audit log
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/agents/organizations/{org_uuid}/{agent_uuid}/",
                method="DELETE",
                status_code=204,
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            assert audit_log is not None, "Audit log entry should be created"
            assert audit_log.success is True, "Audit log should mark success as True"
            assert audit_log.user_id == user.id, "Audit log should reference correct user"
            
            # Verify DataChangeLog for DELETE operation
            if DataChangeLog:
                data_change_log = DataChangeLog.objects.using('default').filter(
                    app_label="agents",
                    model_name="Agent",
                    action="delete",
                    object_id=agent_uuid,
                    created_at__gte=before_request - timedelta(seconds=1)
                ).order_by("-created_at").first()
                
                assert data_change_log is not None, "DataChangeLog entry should be created for DELETE"
                assert data_change_log.audit_log_id == audit_log.id, \
                    f"DataChangeLog audit_log_id should match AuditLog id"
                assert data_change_log.user_id == user.id, \
                    f"DataChangeLog user_id should match user"
                
                # Verify changed_fields contains deleted_at
                changed_fields = data_change_log.changed_fields
                assert "deleted_at" in changed_fields or "state" in changed_fields, \
                    "changed_fields should contain 'deleted_at' or 'state' for DELETE"


@pytest.mark.acceptance
class TestREQAgents002SaveAndManageAgentVersions:
    """REQ-AGENTS-002: Save and Manage Agent Versions"""

    def test_2_1_save_version_with_llm_config(self, authenticated_client, http_client):
        """Test Scenario 2.1: Save version with LLM configuration"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
            
            # Enable an LLM for the organization
            super_admin = User.objects.using('default').filter(email=get_user_credentials("Super Admin")[0]).first()
            if super_admin:
                enable_llm_for_org(org, "gpt-4", super_admin)
        else:
            pytest.skip("Django models not available")
        
        # Create agent
        create_payload = {
            "organization": org_uuid,
            "name": f"Version Test Agent {int(time.time())}",
            "description": "Test agent"
        }
        create_response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=create_payload)
        assert create_response.status_code == 201
        agent_uuid = create_response.json().get("uuid") or create_response.json().get("id")
        
        # Save version with LLM config
        version_payload = {
            "llmConfiguration": {
                "modelKey": "gpt-4",
                "temperature": 0.7,
                "maxTokens": 1000
            },
            "systemPrompts": ["You are a helpful assistant."]
        }
        
        before_request = timezone.now()
        response = make_request(client, "post", f"/agents/organizations/{org_uuid}/{agent_uuid}/versions/", json=version_payload)
        
        assert response.status_code == 201, \
            f"Expected 201 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        assert "version" in data or "versionNumber" in data, "Response should contain version number"
        version_number = data.get("version") or data.get("versionNumber")
        assert version_number == 1, "First version should be version 1"
        
        # Verify database state
        if DJANGO_AVAILABLE and AgentVersion:
            version = AgentVersion.objects.using('default').filter(
                agent__uuid=agent_uuid,
                version_number=1
            ).first()
            assert version is not None, "AgentVersion should exist"
            assert version.llm_configuration is not None, "LLM configuration should be saved"
            assert version.system_prompts == ["You are a helpful assistant."], "System prompts should match"
            
            # Verify agent convenience fields are updated
            agent = Agent.objects.using('default').filter(uuid=agent_uuid).first()
            assert agent.current_version_id == version.id, "Agent currentVersionId should be set"
            assert agent.llm_configuration is not None, "Agent convenience llmConfiguration should be set"
        
        # Verify audit log
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/agents/organizations/{org_uuid}/{agent_uuid}/versions/",
                method="POST",
                status_code=201,
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            assert audit_log is not None, "Audit log entry should be created"
            assert audit_log.success is True, "Audit log should mark success as True"
            assert audit_log.user_id == user.id, "Audit log should reference correct user"
            
            # Verify DataChangeLog for CREATE operation on AgentVersion
            if DataChangeLog:
                data_change_log = DataChangeLog.objects.using('default').filter(
                    app_label="agents",
                    model_name="AgentVersion",
                    action="create",
                    created_at__gte=before_request - timedelta(seconds=1)
                ).order_by("-created_at").first()
                
                assert data_change_log is not None, "DataChangeLog entry should be created for AgentVersion CREATE"

    def test_2_2_save_version_without_llm_rejected(self, authenticated_client, http_client):
        """Test Scenario 2.2: Save version without LLM configuration is rejected"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Create agent
        create_payload = {
            "organization": org_uuid,
            "name": f"No LLM Version Test {int(time.time())}",
            "description": "Test agent"
        }
        create_response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=create_payload)
        assert create_response.status_code == 201
        agent_uuid = create_response.json().get("uuid") or create_response.json().get("id")
        
        # Try to save version without LLM config
        version_payload = {
            "systemPrompts": ["You are a helpful assistant."]
        }
        
        response = make_request(client, "post", f"/agents/organizations/{org_uuid}/{agent_uuid}/versions/", json=version_payload)
        
        assert response.status_code == 400, \
            f"Expected 400 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        assert "llm" in str(data).lower() or "required" in str(data).lower(), \
            "Error should indicate LLM configuration is required"

    def test_2_3_save_version_with_disabled_llm_rejected(self, authenticated_client, http_client):
        """Test Scenario 2.3: Save version with disabled LLM is rejected"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Create agent
        create_payload = {
            "organization": org_uuid,
            "name": f"Disabled LLM Test {int(time.time())}",
            "description": "Test agent"
        }
        create_response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=create_payload)
        assert create_response.status_code == 201
        agent_uuid = create_response.json().get("uuid") or create_response.json().get("id")
        
        # Try to save version with disabled LLM
        version_payload = {
            "llmConfiguration": {
                "modelKey": "gpt-4",
                "temperature": 0.7
            },
            "systemPrompts": ["You are a helpful assistant."]
        }
        
        response = make_request(client, "post", f"/agents/organizations/{org_uuid}/{agent_uuid}/versions/", json=version_payload)
        
        assert response.status_code in [400, 403], \
            f"Expected 400 or 403 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        assert "disabled" in str(data).lower() or "enabled" in str(data).lower() or "not available" in str(data).lower(), \
            "Error should indicate LLM is not enabled for organization"

    def test_2_4_save_version_with_tools(self, authenticated_client, http_client):
        """Test Scenario 2.4: Save version with tools configuration"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            ensure_llm_management_subscription(org)
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
            
            # Enable LLM and tool
            super_admin = User.objects.using('default').filter(email=get_user_credentials("Super Admin")[0]).first()
            if super_admin:
                enable_llm_for_org(org, "gpt-4", super_admin)
                enable_tool_for_org(org, "kb_retriever", super_admin)
        else:
            pytest.skip("Django models not available")
        
        # Create agent
        create_payload = {
            "organization": org_uuid,
            "name": f"Tools Version Test {int(time.time())}",
            "description": "Test agent"
        }
        create_response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=create_payload)
        assert create_response.status_code == 201
        agent_uuid = create_response.json().get("uuid") or create_response.json().get("id")
        
        # Save version with LLM and tools
        version_payload = {
            "llmConfiguration": {
                "modelKey": "gpt-4",
                "temperature": 0.7
            },
            "toolsConfiguration": {
                "tools": [
                    {
                        "toolKey": "kb_retriever",
                        "enabled": True,
                        "configuration": {}
                    }
                ]
            },
            "systemPrompts": ["You are a helpful assistant."]
        }
        
        response = make_request(client, "post", f"/agents/organizations/{org_uuid}/{agent_uuid}/versions/", json=version_payload)
        
        assert response.status_code == 201, \
            f"Expected 201 but got {response.status_code}, response: {response.text}"
        
        # Verify database state
        if DJANGO_AVAILABLE and AgentVersion:
            version = AgentVersion.objects.using('default').filter(
                agent__uuid=agent_uuid,
                version_number=1
            ).first()
            assert version is not None, "AgentVersion should exist"
            assert version.tools_configuration is not None, "Tools configuration should be saved"
            
            # Verify agent convenience fields
            agent = Agent.objects.using('default').filter(uuid=agent_uuid).first()
            assert agent.tools_configuration is not None, "Agent convenience toolsConfiguration should be set"

    def test_2_5_list_versions(self, authenticated_client, http_client):
        """Test Scenario 2.5: List agent versions"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
            
            super_admin = User.objects.using('default').filter(email=get_user_credentials("Super Admin")[0]).first()
            if super_admin:
                enable_llm_for_org(org, "gpt-4", super_admin)
        else:
            pytest.skip("Django models not available")
        
        # Create agent and save versions
        create_payload = {
            "organization": org_uuid,
            "name": f"List Versions Test {int(time.time())}",
            "description": "Test agent"
        }
        create_response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=create_payload)
        assert create_response.status_code == 201
        agent_uuid = create_response.json().get("uuid") or create_response.json().get("id")
        
        # Save version 1
        version1_payload = {
            "llmConfiguration": {
                "modelKey": "gpt-4",
                "temperature": 0.7
            },
            "systemPrompts": ["Version 1 prompt"]
        }
        make_request(client, "post", f"/agents/organizations/{org_uuid}/{agent_uuid}/versions/", json=version1_payload)
        
        # Save version 2
        version2_payload = {
            "llmConfiguration": {
                "modelKey": "gpt-4",
                "temperature": 0.8
            },
            "systemPrompts": ["Version 2 prompt"]
        }
        make_request(client, "post", f"/agents/organizations/{org_uuid}/{agent_uuid}/versions/", json=version2_payload)
        
        # List versions
        response = make_request(client, "get", f"/agents/organizations/{org_uuid}/{agent_uuid}/versions/")
        
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        assert isinstance(data, (list, dict)), "Response should be a list or dict with results"
        
        if isinstance(data, dict):
            versions = data.get("results", data.get("data", []))
        else:
            versions = data
        
        assert len(versions) >= 2, "Should have at least 2 versions"
        assert any(v.get("version") == 1 or v.get("versionNumber") == 1 for v in versions), \
            "Version 1 should be in list"
        assert any(v.get("version") == 2 or v.get("versionNumber") == 2 for v in versions), \
            "Version 2 should be in list"


@pytest.mark.acceptance
class TestREQAgents003SwitchBetweenAgentVersions:
    """REQ-AGENTS-003: Switch Between Agent Versions"""

    def test_3_1_switch_to_different_version(self, authenticated_client, http_client):
        """Test Scenario 3.1: Switch agent to different version"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
            
            super_admin = User.objects.using('default').filter(email=get_user_credentials("Super Admin")[0]).first()
            if super_admin:
                enable_llm_for_org(org, "gpt-4", super_admin)
        else:
            pytest.skip("Django models not available")
        
        # Create agent and save versions
        create_payload = {
            "organization": org_uuid,
            "name": f"Switch Version Test {int(time.time())}",
            "description": "Test agent"
        }
        create_response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=create_payload)
        assert create_response.status_code == 201
        agent_uuid = create_response.json().get("uuid") or create_response.json().get("id")
        
        # Save version 1
        version1_payload = {
            "llmConfiguration": {
                "modelKey": "gpt-4",
                "temperature": 0.7
            },
            "systemPrompts": ["Version 1"]
        }
        make_request(client, "post", f"/agents/organizations/{org_uuid}/{agent_uuid}/versions/", json=version1_payload)
        
        # Save version 2
        version2_payload = {
            "llmConfiguration": {
                "modelKey": "gpt-4",
                "temperature": 0.8
            },
            "systemPrompts": ["Version 2"]
        }
        make_request(client, "post", f"/agents/organizations/{org_uuid}/{agent_uuid}/versions/", json=version2_payload)
        
        # Switch to version 1
        before_request = timezone.now()
        switch_payload = {
            "versionNumber": 1
        }
        response = make_request(client, "post", f"/agents/organizations/{org_uuid}/{agent_uuid}/switch-version/", json=switch_payload)
        
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        assert data.get("currentVersion") == 1 or data.get("currentVersionNumber") == 1, \
            "Current version should be 1"
        
        # Verify database state
        if DJANGO_AVAILABLE and Agent:
            agent = Agent.objects.using('default').filter(uuid=agent_uuid).first()
            version1 = AgentVersion.objects.using('default').filter(
                agent=agent,
                version_number=1
            ).first()
            assert agent.current_version_id == version1.id, "Agent currentVersionId should point to version 1"
        
        # Verify audit log
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/agents/organizations/{org_uuid}/{agent_uuid}/switch-version/",
                method="POST",
                status_code=200,
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            assert audit_log is not None, "Audit log entry should be created"
            assert audit_log.success is True, "Audit log should mark success as True"
            assert audit_log.user_id == user.id, "Audit log should reference correct user"

    def test_3_2_switch_to_nonexistent_version_rejected(self, authenticated_client, http_client):
        """Test Scenario 3.2: Switch to non-existent version is rejected"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
            
            super_admin = User.objects.using('default').filter(email=get_user_credentials("Super Admin")[0]).first()
            if super_admin:
                enable_llm_for_org(org, "gpt-4", super_admin)
        else:
            pytest.skip("Django models not available")
        
        # Create agent
        create_payload = {
            "organization": org_uuid,
            "name": f"Invalid Version Test {int(time.time())}",
            "description": "Test agent"
        }
        create_response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=create_payload)
        assert create_response.status_code == 201
        agent_uuid = create_response.json().get("uuid") or create_response.json().get("id")
        
        # Try to switch to non-existent version
        switch_payload = {
            "versionNumber": 999
        }
        response = make_request(client, "post", f"/agents/organizations/{org_uuid}/{agent_uuid}/switch-version/", json=switch_payload)
        
        assert response.status_code == 404, \
            f"Expected 404 but got {response.status_code}, response: {response.text}"


@pytest.mark.acceptance
class TestREQAgents004ConfigureAgentLLM:
    """REQ-AGENTS-004: Configure Agent LLM"""

    def test_4_1_configure_llm_with_valid_config(self, authenticated_client, http_client):
        """Test Scenario 4.1: Configure LLM with valid configuration"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
            
            super_admin = User.objects.using('default').filter(email=get_user_credentials("Super Admin")[0]).first()
            if super_admin:
                enable_llm_for_org(org, "gpt-4", super_admin)
        else:
            pytest.skip("Django models not available")
        
        # Create agent
        create_payload = {
            "organization": org_uuid,
            "name": f"LLM Config Test {int(time.time())}",
            "description": "Test agent"
        }
        create_response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=create_payload)
        assert create_response.status_code == 201
        agent_uuid = create_response.json().get("uuid") or create_response.json().get("id")
        
        # Configure LLM
        llm_config = {
            "llmConfiguration": {
                "modelKey": "gpt-4",
                "temperature": 0.7,
                "maxTokens": 1000,
                "topP": 0.9
            },
            "systemPrompts": ["You are a helpful assistant."]
        }
        
        response = make_request(client, "post", f"/agents/organizations/{org_uuid}/{agent_uuid}/versions/", json=llm_config)
        
        assert response.status_code == 201, \
            f"Expected 201 but got {response.status_code}, response: {response.text}"
        
        # Verify configuration is saved
        if DJANGO_AVAILABLE and AgentVersion:
            version = AgentVersion.objects.using('default').filter(
                agent__uuid=agent_uuid,
                version_number=1
            ).first()
            assert version is not None, "Version should exist"
            assert version.llm_configuration is not None, "LLM configuration should be saved"
            config = version.llm_configuration
            assert config.get("modelKey") == "gpt-4", "Model key should match"
            assert config.get("temperature") == 0.7, "Temperature should match"

    def test_4_2_configure_llm_with_invalid_temperature_rejected(self, authenticated_client, http_client):
        """Test Scenario 4.2: Configure LLM with invalid temperature is rejected"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
            
            super_admin = User.objects.using('default').filter(email=get_user_credentials("Super Admin")[0]).first()
            if super_admin:
                enable_llm_for_org(org, "gpt-4", super_admin)
        else:
            pytest.skip("Django models not available")
        
        # Create agent
        create_payload = {
            "organization": org_uuid,
            "name": f"Invalid Temp Test {int(time.time())}",
            "description": "Test agent"
        }
        create_response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=create_payload)
        assert create_response.status_code == 201
        agent_uuid = create_response.json().get("uuid") or create_response.json().get("id")
        
        # Try to configure with invalid temperature
        llm_config = {
            "llmConfiguration": {
                "modelKey": "gpt-4",
                "temperature": 2.5  # Invalid: should be 0-2
            },
            "systemPrompts": ["You are a helpful assistant."]
        }
        
        response = make_request(client, "post", f"/agents/organizations/{org_uuid}/{agent_uuid}/versions/", json=llm_config)
        
        assert response.status_code == 400, \
            f"Expected 400 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        assert "temperature" in str(data).lower() or "invalid" in str(data).lower(), \
            "Error should indicate invalid temperature"


@pytest.mark.acceptance
class TestREQAgents005ConfigureAgentTools:
    """REQ-AGENTS-005: Configure Agent Tools"""

    def test_5_1_configure_tools_with_valid_config(self, authenticated_client, http_client):
        """Test Scenario 5.1: Configure tools with valid configuration"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            ensure_llm_management_subscription(org)
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
            
            super_admin = User.objects.using('default').filter(email=get_user_credentials("Super Admin")[0]).first()
            if super_admin:
                enable_llm_for_org(org, "gpt-4", super_admin)
                enable_tool_for_org(org, "kb_retriever", super_admin)
                enable_tool_for_org(org, "calculator", super_admin)
        else:
            pytest.skip("Django models not available")
        
        # Create agent
        create_payload = {
            "organization": org_uuid,
            "name": f"Tools Config Test {int(time.time())}",
            "description": "Test agent"
        }
        create_response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=create_payload)
        assert create_response.status_code == 201
        agent_uuid = create_response.json().get("uuid") or create_response.json().get("id")
        
        # Configure tools
        tools_config = {
            "llmConfiguration": {
                "modelKey": "gpt-4",
                "temperature": 0.7
            },
            "toolsConfiguration": {
                "tools": [
                    {
                        "toolKey": "kb_retriever",
                        "enabled": True,
                        "configuration": {
                            "maxResults": 5
                        }
                    },
                    {
                        "toolKey": "calculator",
                        "enabled": True,
                        "configuration": {}
                    }
                ]
            },
            "systemPrompts": ["You are a helpful assistant."]
        }
        
        response = make_request(client, "post", f"/agents/organizations/{org_uuid}/{agent_uuid}/versions/", json=tools_config)
        
        assert response.status_code == 201, \
            f"Expected 201 but got {response.status_code}, response: {response.text}"
        
        # Verify configuration is saved
        if DJANGO_AVAILABLE and AgentVersion:
            version = AgentVersion.objects.using('default').filter(
                agent__uuid=agent_uuid,
                version_number=1
            ).first()
            assert version is not None, "Version should exist"
            assert version.tools_configuration is not None, "Tools configuration should be saved"
            config = version.tools_configuration
            assert "tools" in config, "Tools configuration should contain tools array"
            assert len(config["tools"]) == 2, "Should have 2 tools configured"

    def test_5_2_configure_disabled_tool_rejected(self, authenticated_client, http_client):
        """Test Scenario 5.2: Configure disabled tool is rejected"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            ensure_llm_management_subscription(org)
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
            
            super_admin = User.objects.using('default').filter(email=get_user_credentials("Super Admin")[0]).first()
            if super_admin:
                enable_llm_for_org(org, "gpt-4", super_admin)
                # Do NOT enable calculator tool
        else:
            pytest.skip("Django models not available")
        
        # Create agent
        create_payload = {
            "organization": org_uuid,
            "name": f"Disabled Tool Test {int(time.time())}",
            "description": "Test agent"
        }
        create_response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=create_payload)
        assert create_response.status_code == 201
        agent_uuid = create_response.json().get("uuid") or create_response.json().get("id")
        
        # Try to configure disabled tool
        tools_config = {
            "llmConfiguration": {
                "modelKey": "gpt-4",
                "temperature": 0.7
            },
            "toolsConfiguration": {
                "tools": [
                    {
                        "toolKey": "calculator",
                        "enabled": True,
                        "configuration": {}
                    }
                ]
            },
            "systemPrompts": ["You are a helpful assistant."]
        }
        
        response = make_request(client, "post", f"/agents/organizations/{org_uuid}/{agent_uuid}/versions/", json=tools_config)
        
        assert response.status_code in [400, 403], \
            f"Expected 400 or 403 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        assert "disabled" in str(data).lower() or "not available" in str(data).lower() or "enabled" in str(data).lower(), \
            "Error should indicate tool is not enabled for organization"


@pytest.mark.acceptance
class TestREQAgents006CloneAgent:
    """REQ-AGENTS-006: Clone Agent"""

    def test_6_1_clone_agent_success(self, authenticated_client, http_client):
        """Test Scenario 6.1: Clone agent creates new agent with same configuration"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
            
            super_admin = User.objects.using('default').filter(email=get_user_credentials("Super Admin")[0]).first()
            if super_admin:
                enable_llm_for_org(org, "gpt-4", super_admin)
        else:
            pytest.skip("Django models not available")
        
        # Create agent and save version
        create_payload = {
            "organization": org_uuid,
            "name": f"Clone Source Agent {int(time.time())}",
            "description": "Source agent"
        }
        create_response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=create_payload)
        assert create_response.status_code == 201
        source_agent_uuid = create_response.json().get("uuid") or create_response.json().get("id")
        
        # Save version
        version_payload = {
            "llmConfiguration": {
                "modelKey": "gpt-4",
                "temperature": 0.7
            },
            "systemPrompts": ["Source prompt"]
        }
        make_request(client, "post", f"/agents/organizations/{org_uuid}/{source_agent_uuid}/versions/", json=version_payload)
        
        # Clone agent
        clone_payload = {
            "name": f"Cloned Agent {int(time.time())}"
        }
        
        before_request = timezone.now()
        response = make_request(client, "post", f"/agents/organizations/{org_uuid}/{source_agent_uuid}/clone/", json=clone_payload)
        
        assert response.status_code == 201, \
            f"Expected 201 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        cloned_agent_uuid = data.get("uuid") or data.get("id")
        assert cloned_agent_uuid != source_agent_uuid, "Cloned agent should have different UUID"
        assert data.get("name") == clone_payload["name"], "Cloned agent name should match"
        
        # Verify cloned agent has same configuration
        if DJANGO_AVAILABLE and AgentVersion:
            source_version = AgentVersion.objects.using('default').filter(
                agent__uuid=source_agent_uuid,
                version_number=1
            ).first()
            cloned_version = AgentVersion.objects.using('default').filter(
                agent__uuid=cloned_agent_uuid,
                version_number=1
            ).first()
            
            assert cloned_version is not None, "Cloned agent should have version"
            assert cloned_version.llm_configuration == source_version.llm_configuration, \
                "Cloned version should have same LLM configuration"
            assert cloned_version.system_prompts == source_version.system_prompts, \
                "Cloned version should have same system prompts"
        
        # Verify audit log
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/agents/organizations/{org_uuid}/{source_agent_uuid}/clone/",
                method="POST",
                status_code=201,
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            assert audit_log is not None, "Audit log entry should be created"
            assert audit_log.success is True, "Audit log should mark success as True"
            assert audit_log.user_id == user.id, "Audit log should reference correct user"


@pytest.mark.acceptance
class TestREQAgents007SubscriptionRequirementEnforcement:
    """REQ-AGENTS-007: Subscription Requirement Enforcement"""

    def test_7_1_all_endpoints_require_subscription(self, authenticated_client, http_client):
        """Test Scenario 7.1: All agent endpoints require AGENTS_MANAGEMENT subscription"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization and Module:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha3").first()
            if not org:
                pytest.skip("Test organization not found")
            
            # Remove AGENTS_MANAGEMENT subscription
            agents_module = Module.objects.using('default').filter(key="AGENTS_MANAGEMENT").first()
            if agents_module:
                Subscription.objects.using('default').filter(
                    organization=org,
                    module=agents_module
                ).delete()
            
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Test GET /agents/
        response = make_request(client, "get", f"/agents/organizations/{org_uuid}/")
        assert response.status_code in [403, 404], \
            f"GET /agents/ should require subscription, got {response.status_code}"
        
        # Test POST /agents/
        create_payload = {
            "organization": org_uuid,
            "name": f"Test Agent {int(time.time())}",
            "description": "Test"
        }
        response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=create_payload)
        assert response.status_code in [403, 404], \
            f"POST /agents/ should require subscription, got {response.status_code}"


@pytest.mark.acceptance
class TestREQAgents009UpdateAgentWithoutCreatingVersion:
    """REQ-AGENTS-009: Update Agent Without Creating Version"""

    def test_9_1_patch_updates_only_metadata(self, authenticated_client, http_client):
        """Test Scenario 9.1: PATCH updates only name, description, currentVersionId, state"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
            
            super_admin = User.objects.using('default').filter(email=get_user_credentials("Super Admin")[0]).first()
            if super_admin:
                enable_llm_for_org(org, "gpt-4", super_admin)
        else:
            pytest.skip("Django models not available")
        
        # Create agent and save version
        create_payload = {
            "organization": org_uuid,
            "name": f"PATCH Test Agent {int(time.time())}",
            "description": "Original description"
        }
        create_response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=create_payload)
        assert create_response.status_code == 201
        agent_uuid = create_response.json().get("uuid") or create_response.json().get("id")
        
        # Save version
        version_payload = {
            "llmConfiguration": {
                "modelKey": "gpt-4",
                "temperature": 0.7
            },
            "systemPrompts": ["Original prompt"]
        }
        make_request(client, "post", f"/agents/organizations/{org_uuid}/{agent_uuid}/versions/", json=version_payload)
        
        # Count versions before PATCH
        if DJANGO_AVAILABLE and AgentVersion:
            versions_before = AgentVersion.objects.using('default').filter(agent__uuid=agent_uuid).count()
        
        # PATCH update (should NOT create new version)
        patch_payload = {
            "name": "Updated Name",
            "description": "Updated description"
        }
        
        before_request = timezone.now()
        response = make_request(client, "patch", f"/agents/organizations/{org_uuid}/{agent_uuid}/", json=patch_payload)
        
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        assert data.get("name") == "Updated Name", "Name should be updated"
        assert data.get("description") == "Updated description", "Description should be updated"
        
        # Verify no new version was created
        if DJANGO_AVAILABLE and AgentVersion:
            versions_after = AgentVersion.objects.using('default').filter(agent__uuid=agent_uuid).count()
            assert versions_after == versions_before, \
                f"PATCH should not create new version: {versions_before} -> {versions_after}"
        
        # Verify configuration fields are NOT updated by PATCH
        if DJANGO_AVAILABLE and AgentVersion:
            version = AgentVersion.objects.using('default').filter(
                agent__uuid=agent_uuid,
                version_number=1
            ).first()
            assert version.system_prompts == ["Original prompt"], \
                "System prompts should NOT be changed by PATCH"

    def test_9_2_patch_ignores_configuration_fields(self, authenticated_client, http_client):
        """Test Scenario 9.2: PATCH ignores llmConfiguration and toolsConfiguration"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
            
            super_admin = User.objects.using('default').filter(email=get_user_credentials("Super Admin")[0]).first()
            if super_admin:
                enable_llm_for_org(org, "gpt-4", super_admin)
        else:
            pytest.skip("Django models not available")
        
        # Create agent and save version
        create_payload = {
            "organization": org_uuid,
            "name": f"Ignore Config Test {int(time.time())}",
            "description": "Test agent"
        }
        create_response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=create_payload)
        assert create_response.status_code == 201
        agent_uuid = create_response.json().get("uuid") or create_response.json().get("id")
        
        # Save version with original config
        version_payload = {
            "llmConfiguration": {
                "modelKey": "gpt-4",
                "temperature": 0.7
            },
            "systemPrompts": ["Original prompt"]
        }
        make_request(client, "post", f"/agents/organizations/{org_uuid}/{agent_uuid}/versions/", json=version_payload)
        
        # Try to PATCH with configuration fields (should be ignored)
        patch_payload = {
            "name": "Updated Name",
            "llmConfiguration": {
                "modelKey": "gpt-4",
                "temperature": 0.9  # Different value
            },
            "toolsConfiguration": {
                "tools": []
            },
            "systemPrompts": ["Ignored prompt"]
        }
        
        response = make_request(client, "patch", f"/agents/organizations/{org_uuid}/{agent_uuid}/", json=patch_payload)
        
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        # Verify configuration was NOT changed
        if DJANGO_AVAILABLE and AgentVersion:
            version = AgentVersion.objects.using('default').filter(
                agent__uuid=agent_uuid,
                version_number=1
            ).first()
            assert version.llm_configuration.get("temperature") == 0.7, \
                "LLM configuration should NOT be changed by PATCH"
            assert version.system_prompts == ["Original prompt"], \
                "System prompts should NOT be changed by PATCH"


@pytest.mark.acceptance
class TestREQAgents010ValidateAgentConfiguration:
    """REQ-AGENTS-010: Validate Agent Configuration"""

    def test_10_1_validate_system_prompts_length(self, authenticated_client, http_client):
        """Test Scenario 10.1: System prompts validation (max length)"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
            
            super_admin = User.objects.using('default').filter(email=get_user_credentials("Super Admin")[0]).first()
            if super_admin:
                enable_llm_for_org(org, "gpt-4", super_admin)
        else:
            pytest.skip("Django models not available")
        
        # Create agent
        create_payload = {
            "organization": org_uuid,
            "name": f"Validation Test {int(time.time())}",
            "description": "Test agent"
        }
        create_response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=create_payload)
        assert create_response.status_code == 201
        agent_uuid = create_response.json().get("uuid") or create_response.json().get("id")
        
        # Try to save version with invalid system prompt (too long)
        long_prompt = "x" * 10001  # Exceeds max length
        version_payload = {
            "llmConfiguration": {
                "modelKey": "gpt-4",
                "temperature": 0.7
            },
            "systemPrompts": [long_prompt]
        }
        
        response = make_request(client, "post", f"/agents/organizations/{org_uuid}/{agent_uuid}/versions/", json=version_payload)
        
        assert response.status_code == 400, \
            f"Expected 400 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        assert "prompt" in str(data).lower() or "length" in str(data).lower() or "max" in str(data).lower(), \
            "Error should indicate system prompt length violation"

    def test_10_2_validate_name_characters(self, authenticated_client, http_client):
        """Test Scenario 10.2: Agent name validation (allowed characters)"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Try to create agent with invalid characters in name
        invalid_payload = {
            "organization": org_uuid,
            "name": "Test Agent <script>alert('xss')</script>",
            "description": "Test"
        }
        
        response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=invalid_payload)
        
        assert response.status_code == 400, \
            f"Expected 400 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        assert "name" in str(data).lower() or "invalid" in str(data).lower() or "character" in str(data).lower(), \
            "Error should indicate invalid characters in name"


@pytest.mark.acceptance
class TestREQAgents011SoftDeleteAgents:
    """REQ-AGENTS-011: Soft Delete Agents"""

    def test_11_1_deleted_agent_not_in_list(self, authenticated_client, http_client):
        """Test Scenario 11.1: Deleted agent does not appear in list"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Create agent
        create_payload = {
            "organization": org_uuid,
            "name": f"Soft Delete Test {int(time.time())}",
            "description": "Test agent"
        }
        create_response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=create_payload)
        assert create_response.status_code == 201
        agent_uuid = create_response.json().get("uuid") or create_response.json().get("id")
        
        # Delete agent
        make_request(client, "delete", f"/agents/organizations/{org_uuid}/{agent_uuid}/")
        
        # List agents - deleted agent should not appear
        response = make_request(client, "get", f"/agents/organizations/{org_uuid}/")
        
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        if isinstance(data, dict):
            agents = data.get("results", data.get("data", []))
        else:
            agents = data
        
        agent_uuids = [a.get("uuid") or a.get("id") for a in agents]
        assert agent_uuid not in agent_uuids, "Deleted agent should not appear in list"

    def test_11_2_deleted_agent_not_accessible(self, authenticated_client, http_client):
        """Test Scenario 11.2: Deleted agent cannot be accessed"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Create agent
        create_payload = {
            "organization": org_uuid,
            "name": f"Access Deleted Test {int(time.time())}",
            "description": "Test agent"
        }
        create_response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=create_payload)
        assert create_response.status_code == 201
        agent_uuid = create_response.json().get("uuid") or create_response.json().get("id")
        
        # Delete agent
        make_request(client, "delete", f"/agents/organizations/{org_uuid}/{agent_uuid}/")
        
        # Try to get deleted agent
        response = make_request(client, "get", f"/agents/organizations/{org_uuid}/{agent_uuid}/")
        
        assert response.status_code == 404, \
            f"Expected 404 but got {response.status_code}, response: {response.text}"


@pytest.mark.acceptance
class TestInvalidPayloadsAndErrorScenarios:
    """Tests for invalid payloads and error scenarios"""

    def test_invalid_llm_not_enabled(self, authenticated_client, http_client):
        """Test: Trying to add an LLM that was not enabled is rejected"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
            
            # Do NOT enable any LLM for the organization
        else:
            pytest.skip("Django models not available")
        
        # Create agent
        create_payload = {
            "organization": org_uuid,
            "name": f"Invalid LLM Test {int(time.time())}",
            "description": "Test agent"
        }
        create_response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=create_payload)
        assert create_response.status_code == 201
        agent_uuid = create_response.json().get("uuid") or create_response.json().get("id")
        
        # Try to save version with non-enabled LLM
        version_payload = {
            "llmConfiguration": {
                "modelKey": "gpt-4",
                "temperature": 0.7
            },
            "systemPrompts": ["Test prompt"]
        }
        
        response = make_request(client, "post", f"/agents/organizations/{org_uuid}/{agent_uuid}/versions/", json=version_payload)
        
        assert response.status_code in [400, 403, 404], \
            f"Expected 400, 403, or 404 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        assert "not enabled" in str(data).lower() or "not available" in str(data).lower() or "disabled" in str(data).lower() or "enabled" in str(data).lower(), \
            "Error should indicate LLM is not enabled for organization"

    def test_invalid_tool_not_enabled(self, authenticated_client, http_client):
        """Test: Trying to add a tool that was not enabled is rejected"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            ensure_llm_management_subscription(org)
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
            
            super_admin = User.objects.using('default').filter(email=get_user_credentials("Super Admin")[0]).first()
            if super_admin:
                enable_llm_for_org(org, "gpt-4", super_admin)
                # Do NOT enable calculator tool
        else:
            pytest.skip("Django models not available")
        
        # Create agent
        create_payload = {
            "organization": org_uuid,
            "name": f"Invalid Tool Test {int(time.time())}",
            "description": "Test agent"
        }
        create_response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=create_payload)
        assert create_response.status_code == 201
        agent_uuid = create_response.json().get("uuid") or create_response.json().get("id")
        
        # Try to save version with non-enabled tool
        version_payload = {
            "llmConfiguration": {
                "modelKey": "gpt-4",
                "temperature": 0.7
            },
            "toolsConfiguration": {
                "tools": [
                    {
                        "toolKey": "calculator",
                        "enabled": True,
                        "configuration": {}
                    }
                ]
            },
            "systemPrompts": ["Test prompt"]
        }
        
        response = make_request(client, "post", f"/agents/organizations/{org_uuid}/{agent_uuid}/versions/", json=version_payload)
        
        assert response.status_code in [400, 403], \
            f"Expected 400 or 403 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        assert "not enabled" in str(data).lower() or "not available" in str(data).lower() or "disabled" in str(data).lower() or "enabled" in str(data).lower(), \
            "Error should indicate tool is not enabled for organization"

    def test_invalid_llm_subscription_removed(self, authenticated_client, http_client):
        """Test: Trying to add an LLM that was enabled but LLM_MANAGEMENT subscription was removed"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization and Module:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
            
            super_admin = User.objects.using('default').filter(email=get_user_credentials("Super Admin")[0]).first()
            if super_admin:
                enable_llm_for_org(org, "gpt-4", super_admin)
            
            # Create agent and save version with LLM
            create_payload = {
                "organization": org_uuid,
                "name": f"Subscription Removed Test {int(time.time())}",
                "description": "Test agent"
            }
            create_response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=create_payload)
            assert create_response.status_code == 201
            agent_uuid = create_response.json().get("uuid") or create_response.json().get("id")
            
            version_payload = {
                "llmConfiguration": {
                    "modelKey": "gpt-4",
                    "temperature": 0.7
                },
                "systemPrompts": ["Test prompt"]
            }
            make_request(client, "post", f"/agents/organizations/{org_uuid}/{agent_uuid}/versions/", json=version_payload)
            
            # Remove LLM_MANAGEMENT subscription
            llm_module = Module.objects.using('default').filter(key="LLM_MANAGEMENT").first()
            if llm_module:
                Subscription.objects.using('default').filter(
                    organization=org,
                    module=llm_module
                ).delete()
            
            # Try to save a new version - should fail because subscription is removed
            version_payload2 = {
                "llmConfiguration": {
                    "modelKey": "gpt-4",
                    "temperature": 0.8
                },
                "systemPrompts": ["Updated prompt"]
            }
            
            response = make_request(client, "post", f"/agents/organizations/{org_uuid}/{agent_uuid}/versions/", json=version_payload2)
            
            assert response.status_code in [400, 403, 404], \
                f"Expected 400, 403, or 404 but got {response.status_code}, response: {response.text}"
            
            data = response.json()
            assert "subscription" in str(data).lower() or "not available" in str(data).lower() or "enabled" in str(data).lower(), \
                "Error should indicate subscription is required or LLM is not available"
        else:
            pytest.skip("Django models not available")

    def test_invalid_tool_subscription_removed(self, authenticated_client, http_client):
        """Test: Trying to add a tool that was enabled but TOOLS_MANAGEMENT subscription was removed"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization and Module:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            ensure_llm_management_subscription(org)
            ensure_tools_management_subscription(org)
            org_uuid = str(org.uuid)
            
            super_admin = User.objects.using('default').filter(email=get_user_credentials("Super Admin")[0]).first()
            if super_admin:
                enable_llm_for_org(org, "gpt-4", super_admin)
                enable_tool_for_org(org, "kb_retriever", super_admin)
            
            # Create agent and save version with tool
            create_payload = {
                "organization": org_uuid,
                "name": f"Tool Subscription Removed Test {int(time.time())}",
                "description": "Test agent"
            }
            create_response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=create_payload)
            assert create_response.status_code == 201
            agent_uuid = create_response.json().get("uuid") or create_response.json().get("id")
            
            version_payload = {
                "llmConfiguration": {
                    "modelKey": "gpt-4",
                    "temperature": 0.7
                },
                "toolsConfiguration": {
                    "tools": [
                        {
                            "toolKey": "kb_retriever",
                            "enabled": True,
                            "configuration": {}
                        }
                    ]
                },
                "systemPrompts": ["Test prompt"]
            }
            make_request(client, "post", f"/agents/organizations/{org_uuid}/{agent_uuid}/versions/", json=version_payload)
            
            # Remove TOOLS_MANAGEMENT subscription
            tools_module = Module.objects.using('default').filter(key="TOOLS_MANAGEMENT").first()
            if tools_module:
                Subscription.objects.using('default').filter(
                    organization=org,
                    module=tools_module
                ).delete()
            
            # Try to save a new version with tool - should fail because subscription is removed
            version_payload2 = {
                "llmConfiguration": {
                    "modelKey": "gpt-4",
                    "temperature": 0.7
                },
                "toolsConfiguration": {
                    "tools": [
                        {
                            "toolKey": "kb_retriever",
                            "enabled": True,
                            "configuration": {}
                        }
                    ]
                },
                "systemPrompts": ["Updated prompt"]
            }
            
            response = make_request(client, "post", f"/agents/organizations/{org_uuid}/{agent_uuid}/versions/", json=version_payload2)
            
            assert response.status_code in [400, 403, 404], \
                f"Expected 400, 403, or 404 but got {response.status_code}, response: {response.text}"
            
            data = response.json()
            assert "subscription" in str(data).lower() or "not available" in str(data).lower() or "enabled" in str(data).lower(), \
                "Error should indicate subscription is required or tool is not available"
        else:
            pytest.skip("Django models not available")

    def test_invalid_characters_in_description(self, authenticated_client, http_client):
        """Test: Trying unallowed characters in description is rejected"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Try to create agent with invalid characters in description
        invalid_payload = {
            "organization": org_uuid,
            "name": f"Invalid Desc Test {int(time.time())}",
            "description": "Test description <script>alert('xss')</script>"
        }
        
        response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=invalid_payload)
        
        assert response.status_code == 400, \
            f"Expected 400 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        assert "description" in str(data).lower() or "invalid" in str(data).lower() or "character" in str(data).lower(), \
            "Error should indicate invalid characters in description"

    def test_invalid_characters_in_system_prompts(self, authenticated_client, http_client):
        """Test: Trying unallowed characters in system prompts is rejected"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
            
            super_admin = User.objects.using('default').filter(email=get_user_credentials("Super Admin")[0]).first()
            if super_admin:
                enable_llm_for_org(org, "gpt-4", super_admin)
        else:
            pytest.skip("Django models not available")
        
        # Create agent
        create_payload = {
            "organization": org_uuid,
            "name": f"Invalid Prompt Test {int(time.time())}",
            "description": "Test agent"
        }
        create_response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=create_payload)
        assert create_response.status_code == 201
        agent_uuid = create_response.json().get("uuid") or create_response.json().get("id")
        
        # Try to save version with invalid characters in system prompts
        version_payload = {
            "llmConfiguration": {
                "modelKey": "gpt-4",
                "temperature": 0.7
            },
            "systemPrompts": ["Valid prompt", "<script>alert('xss')</script>"]
        }
        
        response = make_request(client, "post", f"/agents/organizations/{org_uuid}/{agent_uuid}/versions/", json=version_payload)
        
        assert response.status_code == 400, \
            f"Expected 400 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        assert "prompt" in str(data).lower() or "invalid" in str(data).lower() or "character" in str(data).lower(), \
            "Error should indicate invalid characters in system prompts"

    def test_access_nonexistent_version(self, authenticated_client, http_client):
        """Test: Trying to access a version that does not exist is rejected"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
            
            super_admin = User.objects.using('default').filter(email=get_user_credentials("Super Admin")[0]).first()
            if super_admin:
                enable_llm_for_org(org, "gpt-4", super_admin)
        else:
            pytest.skip("Django models not available")
        
        # Create agent and save version
        create_payload = {
            "organization": org_uuid,
            "name": f"Nonexistent Version Test {int(time.time())}",
            "description": "Test agent"
        }
        create_response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=create_payload)
        assert create_response.status_code == 201
        agent_uuid = create_response.json().get("uuid") or create_response.json().get("id")
        
        version_payload = {
            "llmConfiguration": {
                "modelKey": "gpt-4",
                "temperature": 0.7
            },
            "systemPrompts": ["Test prompt"]
        }
        version_response = make_request(client, "post", f"/agents/organizations/{org_uuid}/{agent_uuid}/versions/", json=version_payload)
        assert version_response.status_code == 201
        version_uuid = version_response.json().get("uuid") or version_response.json().get("id")
        
        # Try to access non-existent version
        fake_version_uuid = "00000000-0000-0000-0000-000000000000"
        response = make_request(client, "get", f"/agents/organizations/{org_uuid}/{agent_uuid}/versions/{fake_version_uuid}/")
        
        assert response.status_code == 404, \
            f"Expected 404 but got {response.status_code}, response: {response.text}"

    def test_edit_nonexistent_version(self, authenticated_client, http_client):
        """Test: Trying to edit a version that does not exist is rejected"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
            
            super_admin = User.objects.using('default').filter(email=get_user_credentials("Super Admin")[0]).first()
            if super_admin:
                enable_llm_for_org(org, "gpt-4", super_admin)
        else:
            pytest.skip("Django models not available")
        
        # Create agent
        create_payload = {
            "organization": org_uuid,
            "name": f"Edit Nonexistent Version Test {int(time.time())}",
            "description": "Test agent"
        }
        create_response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=create_payload)
        assert create_response.status_code == 201
        agent_uuid = create_response.json().get("uuid") or create_response.json().get("id")
        
        # Try to edit non-existent version
        fake_version_uuid = "00000000-0000-0000-0000-000000000000"
        update_payload = {
            "llmConfiguration": {
                "modelKey": "gpt-4",
                "temperature": 0.8
            },
            "systemPrompts": ["Updated prompt"]
        }
        
        response = make_request(client, "put", f"/agents/organizations/{org_uuid}/{agent_uuid}/versions/{fake_version_uuid}/", json=update_payload)
        
        assert response.status_code == 404, \
            f"Expected 404 but got {response.status_code}, response: {response.text}"

    def test_access_agent_invalid_id(self, authenticated_client, http_client):
        """Test: Trying to access an agent with invalid ID is rejected"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Try to access agent with invalid UUID
        invalid_uuid = "invalid-uuid-format"
        response = make_request(client, "get", f"/agents/organizations/{org_uuid}/{invalid_uuid}/")
        
        assert response.status_code in [400, 404], \
            f"Expected 400 or 404 but got {response.status_code}, response: {response.text}"
        
        # Try to access agent with non-existent UUID
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        response2 = make_request(client, "get", f"/agents/organizations/{org_uuid}/{fake_uuid}/")
        
        assert response2.status_code == 404, \
            f"Expected 404 but got {response2.status_code}, response: {response2.text}"

    def test_edit_agent_invalid_id(self, authenticated_client, http_client):
        """Test: Trying to edit an agent with invalid ID is rejected"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Try to edit agent with invalid UUID
        invalid_uuid = "invalid-uuid-format"
        update_payload = {
            "name": "Updated Name",
            "description": "Updated description"
        }
        response = make_request(client, "patch", f"/agents/organizations/{org_uuid}/{invalid_uuid}/", json=update_payload)
        
        assert response.status_code in [400, 404], \
            f"Expected 400 or 404 but got {response.status_code}, response: {response.text}"
        
        # Try to edit agent with non-existent UUID
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        response2 = make_request(client, "patch", f"/agents/organizations/{org_uuid}/{fake_uuid}/", json=update_payload)
        
        assert response2.status_code == 404, \
            f"Expected 404 but got {response2.status_code}, response: {response2.text}"

    def test_switch_to_nonexistent_version(self, authenticated_client, http_client):
        """Test: Trying to switch to a version that does not exist is rejected"""
        email, password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email, password)
        
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_agents_management_subscription(org)
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
            
            super_admin = User.objects.using('default').filter(email=get_user_credentials("Super Admin")[0]).first()
            if super_admin:
                enable_llm_for_org(org, "gpt-4", super_admin)
        else:
            pytest.skip("Django models not available")
        
        # Create agent
        create_payload = {
            "organization": org_uuid,
            "name": f"Switch Nonexistent Version Test {int(time.time())}",
            "description": "Test agent"
        }
        create_response = make_request(client, "post", f"/agents/organizations/{org_uuid}/", json=create_payload)
        assert create_response.status_code == 201
        agent_uuid = create_response.json().get("uuid") or create_response.json().get("id")
        
        # Try to switch to non-existent version
        switch_payload = {
            "versionNumber": 999
        }
        response = make_request(client, "post", f"/agents/organizations/{org_uuid}/{agent_uuid}/switch-version/", json=switch_payload)
        
        assert response.status_code == 404, \
            f"Expected 404 but got {response.status_code}, response: {response.text}"
        
        # Also try with invalid version UUID if the endpoint accepts UUID
        fake_version_uuid = "00000000-0000-0000-0000-000000000000"
        switch_payload2 = {
            "versionUuid": fake_version_uuid
        }
        response2 = make_request(client, "post", f"/agents/organizations/{org_uuid}/{agent_uuid}/switch-version/", json=switch_payload2)
        
        # Should either reject with 400 (invalid format) or 404 (not found)
        assert response2.status_code in [400, 404], \
            f"Expected 400 or 404 but got {response2.status_code}, response: {response2.text}"
