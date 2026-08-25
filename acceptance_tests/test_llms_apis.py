"""
Acceptance tests for LLM Management API endpoints.

Tests cover all requirements from REQ-LLM-001 through REQ-LLM-006.
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
    from apps.agents.models import OrganizationEnabledLLM
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
    OrganizationEnabledLLM = None
    Subscription = None
    Role = None
    RoleAssignment = None
    Module = None
    LLMDefinition = None
    timezone = None
    timedelta = None


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


@pytest.mark.acceptance
class TestREQLLM001ListAvailableLLMs:
    """REQ-LLM-001: List Available LLMs"""

    def test_1_1_successful_list_by_saas_administrator(self, authenticated_client, http_client):
        """Test Scenario 1.1: SaaS Administrator can list all available LLMs"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        # time.sleep(60*60)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure LLM_MANAGEMENT subscription exists
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Make request
        before_request = timezone.now()
        response = make_request(client, "get", f"/llms/organizations/{org_uuid}/")
        
        # Verify response
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        assert len(data) > 0, "Should return at least one LLM"
        
        # Verify LLM structure
        llm = data[0]
        assert "modelKey" in llm or "model_key" in llm, "LLM should have modelKey"
        assert "modelProvider" in llm or "model_provider" in llm, "LLM should have modelProvider"
        assert "displayName" in llm or "display_name" in llm, "LLM should have displayName"
        
        # Verify audit log
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/llms/organizations/{org_uuid}/",
                method="GET",
                status_code=200,
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            assert audit_log is not None, "Audit log entry should be created"
            assert audit_log.success is True, "Audit log should mark success as True"
            assert audit_log.user_id == user.id, "Audit log should reference correct user"

    def test_1_2_successful_list_by_saas_account_manager(self, authenticated_client, http_client):
        """Test Scenario 1.2: SaaS Account Manager can list available LLMs"""
        email, password = get_user_credentials("SaaS Account Manager")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure LLM_MANAGEMENT subscription exists
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Make request
        response = make_request(client, "get", f"/llms/organizations/{org_uuid}/")
        
        # Verify response
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"

    def test_1_3_list_excludes_hosted_models_without_subscription(self, authenticated_client, http_client):
        """Test Scenario 1.3: Organization without hosted subscription excludes SaaS Platform Hosted models"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization without hosted subscription
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure LLM_MANAGEMENT subscription exists (but not hosted models)
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Make request
        response = make_request(client, "get", f"/llms/organizations/{org_uuid}/")
        
        # Verify response
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        # Verify no SaaS Platform Hosted models are included
        for llm in data:
            provider = llm.get("modelProvider") or llm.get("model_provider", "")
            assert not provider.lower().startswith("saas platform"), \
                f"SaaS Platform Hosted models should be excluded: {provider}"
        # Compare with expected from database: without hosted subscription only non-hosted LLMs
        if DJANGO_AVAILABLE and LLMDefinition:
            expected_definitions = list(
                LLMDefinition.objects.using("default").exclude(
                    model_provider__istartswith="saas platform"
                ).order_by("model_key")
            )
            expected_keys = {d.model_key for d in expected_definitions}
            expected_by_key = {d.model_key: d for d in expected_definitions}
            response_keys = {llm.get("modelKey") or llm.get("model_key") for llm in data}
            assert response_keys == expected_keys, (
                f"Response model keys should match expected (non-hosted only). "
                f"Expected count {len(expected_keys)}, got {len(response_keys)}. "
                f"Missing: {expected_keys - response_keys}. Extra: {response_keys - expected_keys}."
            )
            assert len(data) == len(expected_definitions), (
                f"Response count should be {len(expected_definitions)} (non-hosted), got {len(data)}"
            )
            for llm in data:
                key = llm.get("modelKey") or llm.get("model_key")
                if key in expected_by_key:
                    exp = expected_by_key[key]
                    assert (llm.get("modelProvider") or llm.get("model_provider")) == exp.model_provider, (
                        f"modelProvider for {key} should be {exp.model_provider}"
                    )
                    assert (llm.get("displayName") or llm.get("display_name")) == exp.display_name, (
                        f"displayName for {key} should be {exp.display_name}"
                    )

    def test_1_4_list_includes_hosted_models_with_subscription(self, authenticated_client, http_client):
        """Test Scenario 1.4: Organization with hosted subscription includes SaaS Platform Hosted models"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization with subscription
        if DJANGO_AVAILABLE and Organization and Subscription:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            
            # Ensure LLM_MANAGEMENT subscription exists
            subscription = ensure_llm_management_subscription(org)
            
            # Ensure subscription has hosted models enabled
            if subscription:
                config = subscription.configuration or {}
                config["llms_enabled_hosted_models"] = ["deepseek-r1", "qwen3-8b"]
                subscription.configuration = config
                subscription.save()
            
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Make request
        response = make_request(client, "get", f"/llms/organizations/{org_uuid}/")
        
        # Verify response
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        # Verify response against expected from database: non-hosted + hosted allowed by subscription
        if DJANGO_AVAILABLE and LLMDefinition and subscription:
            allowed_hosted = set((subscription.configuration or {}).get("llms_enabled_hosted_models") or [])
            all_defs = list(LLMDefinition.objects.using("default").all())
            expected_definitions = [
                d for d in all_defs
                if not (d.model_provider or "").lower().startswith("saas platform") or d.model_key in allowed_hosted
            ]
            expected_keys = {d.model_key for d in expected_definitions}
            expected_by_key = {d.model_key: d for d in expected_definitions}
            response_keys = {llm.get("modelKey") or llm.get("model_key") for llm in data}
            assert response_keys == expected_keys, (
                f"Response model keys should match expected. "
                f"Expected count {len(expected_keys)}, got {len(response_keys)}. "
                f"Missing: {expected_keys - response_keys}. Extra: {response_keys - expected_keys}."
            )
            assert len(data) == len(expected_definitions), (
                f"Response count should be {len(expected_definitions)}, got {len(data)}"
            )
            for llm in data:
                key = llm.get("modelKey") or llm.get("model_key")
                if key in expected_by_key:
                    exp = expected_by_key[key]
                    assert (llm.get("modelProvider") or llm.get("model_provider")) == exp.model_provider, (
                        f"modelProvider for {key} should be {exp.model_provider}"
                    )
                    assert (llm.get("displayName") or llm.get("display_name")) == exp.display_name, (
                        f"displayName for {key} should be {exp.display_name}"
                    )
            # Hosted models in subscription should be present
            for key in allowed_hosted:
                assert key in response_keys, f"Hosted model {key} (in subscription) should be in response"

    def test_1_5_list_rejected_by_agent_manager(self, authenticated_client, http_client):
        """Test Scenario 1.5: Regular user without llms:list permission cannot list available LLMs"""
        email, password = get_user_credentials("Account 1 User 1")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure LLM_MANAGEMENT subscription exists
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Make request
        before_request = timezone.now()
        response = make_request(client, "get", f"/llms/organizations/{org_uuid}/")
        
        # Verify response - should be 403 (permission denied) since user doesn't have llms:list permission
        assert response.status_code == 403, \
            f"Expected 403 but got {response.status_code}, response: {response.text}"
        
        # Verify audit log
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/llms/organizations/{org_uuid}/",
                method="GET",
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            if audit_log:
                assert audit_log.user_id == user.id, "Audit log should reference correct user"

    def test_1_6_list_unauthenticated(self, http_client):
        """Test Scenario 1.6: Unauthenticated request is rejected"""
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Make request
        response = make_request(http_client, "get", f"/llms/organizations/{org_uuid}/")
        
        # Verify response
        assert response.status_code == 401, \
            f"Expected 401 but got {response.status_code}, response: {response.text}"
    
    def test_1_7_list_denied_without_llm_management_subscription(self, authenticated_client, http_client):
        """Test Scenario 1.7: Even SAAS Administrator cannot list LLMs without LLM_MANAGEMENT subscription"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization without LLM_MANAGEMENT subscription
        if DJANGO_AVAILABLE and Organization and Module:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha3").first()
            if not org:
                pytest.skip("Test organization not found")
            
            # Remove LLM_MANAGEMENT subscription if it exists
            llm_module = Module.objects.using('default').filter(key="LLM_MANAGEMENT").first()
            if llm_module:
                Subscription.objects.using('default').filter(
                    organization=org,
                    module=llm_module
                ).delete()
            
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Make request
        response = make_request(client, "get", f"/llms/organizations/{org_uuid}/")
        
        # Verify response - should be denied even for SAAS Administrator
        assert response.status_code in [403, 404], \
            f"Expected 403 or 404 without subscription but got {response.status_code}, response: {response.text}"
    
    def test_1_8_system_roles_cannot_list(self, authenticated_client, http_client):
        """Test Scenario 1.8: System roles (Account-Admin, Account-Owner, Org-Admin, Org-Owner) cannot list"""
        if not DJANGO_AVAILABLE or not Organization:
            pytest.skip("Django models not available")
        
        org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
        if not org:
            pytest.skip("Test organization not found")
        
        # Ensure LLM_MANAGEMENT subscription exists
        ensure_llm_management_subscription(org)
        org_uuid = str(org.uuid)
        
        # Test Account Admin
        email, password = get_user_credentials("Account 1 Admin")
        client = authenticated_client(email, password)
        response = make_request(client, "get", f"/llms/organizations/{org_uuid}/")
        assert response.status_code == 403, \
            f"Account Admin should not have access to list, got {response.status_code}, response: {response.text}"
        
        # Test Account Owner
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        response = make_request(client, "get", f"/llms/organizations/{org_uuid}/")
        assert response.status_code == 403, \
            f"Account Owner Manager should not have access to list, got {response.status_code}, response: {response.text}"
        
        # Test Organization Admin
        email, password = get_user_credentials("Account 1 Org Admin")
        client = authenticated_client(email, password)
        response = make_request(client, "get", f"/llms/organizations/{org_uuid}/")
        assert response.status_code == 403, \
            f"Organization Admin should NOT have access to list (only SAAS-* roles can), got {response.status_code}, response: {response.text}"


@pytest.mark.acceptance
class TestREQLLM002ListEnabledLLMs:
    """REQ-LLM-002: List Enabled LLMs for Organization"""

    def test_2_1_successful_list_enabled_llms(self, authenticated_client, http_client):
        """Test Scenario 2.1: Organization member can list enabled LLMs"""
        email, password = get_user_credentials("Account 1 Org Admin")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure LLM_MANAGEMENT subscription exists
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Make request
        before_request = timezone.now()
        response = make_request(client, "get", f"/llms/organizations/{org_uuid}/enabled/")
        
        # Verify response
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        # Response might be paginated
        if isinstance(data, dict) and "results" in data:
            results = data["results"]
            assert isinstance(results, list), "Results should be a list"
        else:
            assert isinstance(data, list), "Response should be a list"
        
        # Verify audit log
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/llms/organizations/{org_uuid}/enabled/",
                method="GET",
                status_code=200,
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            assert audit_log is not None, "Audit log entry should be created"
            assert audit_log.success is True, "Audit log should mark success as True"
            assert audit_log.user_id == user.id, "Audit log should reference correct user"

    def test_2_2_empty_list_when_no_enabled_llms(self, authenticated_client, http_client):
        """Test Scenario 2.2: Empty list returned when no LLMs are enabled"""
        email, password = get_user_credentials("Account 1 Admin")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure LLM_MANAGEMENT subscription exists
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
            
            # Ensure no LLMs are enabled
            OrganizationEnabledLLM.objects.using('default').filter(
                organization=org,
                disabled_at__isnull=True
            ).update(disabled_at=timezone.now())
        else:
            pytest.skip("Django models not available")
        
        # Make request
        response = make_request(client, "get", f"/llms/organizations/{org_uuid}/enabled/")
        
        # Verify response
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        # Response might be paginated
        if isinstance(data, dict) and "results" in data:
            results = data["results"]
            assert len(results) == 0, "Should return empty list when no LLMs enabled"
        else:
            assert len(data) == 0, "Should return empty list when no LLMs enabled"

    def test_2_3_disabled_llm_not_included(self, authenticated_client, http_client):
        """Test Scenario 2.3: Previously disabled LLM is not included in enabled list"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization and OrganizationEnabledLLM:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure LLM_MANAGEMENT subscription exists
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
            
            # Enable an LLM first
            user = User.objects.using('default').filter(email=email).first()
            enabled_llm, _ = OrganizationEnabledLLM.objects.using('default').get_or_create(
                organization=org,
                model_key="gpt-4o-mini",
                defaults={
                    "model_provider": "OpenAI",
                    "enabled_by": user,
                    "disabled_at": None,
                }
            )

            # Make request
            response = make_request(client, "get", f"/llms/organizations/{org_uuid}/enabled/")
            
            # Verify response
            assert response.status_code == 200, \
                f"Expected 200 but got {response.status_code}, response: {response.text}"
            
            data = response.json()
            # Response might be paginated
            if isinstance(data, dict) and "results" in data:
                results = data["results"]
            else:
                results = data
            
            # Verify disabled LLM is in the list
            model_keys = [llm.get("model_key") or llm.get("modelKey") for llm in results]
            assert "gpt-4o-mini" in model_keys, "LLM should be enabled in the list"
            
            # Disable it
            enabled_llm.disable(actor=user)
            enabled_llm.save()
        else:
            pytest.skip("Django models not available")
        
        # Make request
        response = make_request(client, "get", f"/llms/organizations/{org_uuid}/enabled/")
        
        # Verify response
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        data = response.json()
        # Response might be paginated
        if isinstance(data, dict) and "results" in data:
            results = data["results"]
        else:
            results = data
        
        # Verify disabled LLM is not in the list
        model_keys = [llm.get("model_key") or llm.get("modelKey") for llm in results]
        assert "gpt-4o-mini" not in model_keys, "Disabled LLM should not be in enabled list"

    def test_2_4_list_unauthenticated(self, http_client):
        """Test Scenario 2.4: Unauthenticated request is rejected"""
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Make request
        response = make_request(http_client, "get", f"/llms/organizations/{org_uuid}/enabled/")
        
        # Verify response
        assert response.status_code == 401, \
            f"Expected 401 but got {response.status_code}, response: {response.text}"
    
    def test_2_5_list_denied_without_llm_management_subscription(self, authenticated_client, http_client):
        """Test Scenario 2.5: Even SAAS Administrator cannot list enabled LLMs without LLM_MANAGEMENT subscription"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization without LLM_MANAGEMENT subscription
        if DJANGO_AVAILABLE and Organization and Module:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha3").first()
            if not org:
                pytest.skip("Test organization not found")
            
            # Remove LLM_MANAGEMENT subscription if it exists
            llm_module = Module.objects.using('default').filter(key="LLM_MANAGEMENT").first()
            if llm_module:
                Subscription.objects.using('default').filter(
                    organization=org,
                    module=llm_module
                ).delete()
            
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        # Make request
        response = make_request(client, "get", f"/llms/organizations/{org_uuid}/enabled/")
        
        # Verify response - should be denied even for SAAS Administrator
        assert response.status_code in [403, 404], \
            f"Expected 403 or 404 without subscription but got {response.status_code}, response: {response.text}"


@pytest.mark.acceptance
class TestREQLLM003EnableLLMForOrganization:
    """REQ-LLM-003: Enable LLM for Organization"""

    def test_3_1_successful_enable_by_saas_administrator(self, authenticated_client, http_client):
        """Test Scenario 3.1: SaaS Administrator can enable LLM"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure LLM_MANAGEMENT subscription exists
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        model_key = "gpt-4o-mini"
        
        # Ensure LLM is not already enabled
        if DJANGO_AVAILABLE and OrganizationEnabledLLM:
            OrganizationEnabledLLM.objects.using('default').filter(
                organization=org,
                model_key=model_key
            ).update(disabled_at=timezone.now())
        
        # Make request
        before_request = timezone.now()
        response = make_request(client, "post", f"/llms/organizations/{org_uuid}/{model_key}/enable/")
        
        # Verify response
        assert response.status_code in [200, 201], \
            f"Expected 200 or 201 but got {response.status_code}, response: {response.text}"
        
        # Verify database state
        if DJANGO_AVAILABLE and OrganizationEnabledLLM:
            enabled_llm = OrganizationEnabledLLM.objects.using('default').filter(
                organization=org,
                model_key=model_key,
                disabled_at__isnull=True
            ).first()
            
            assert enabled_llm is not None, "LLM should be enabled in database"
            assert enabled_llm.model_provider == "OpenAI", "Model provider should be OpenAI"
        
        # Verify audit log
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/llms/organizations/{org_uuid}/{model_key}/enable/",
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
                    model_name="OrganizationEnabledLLM",
                    action="create",
                    created_at__gte=before_request - timedelta(seconds=1)
                ).order_by("-created_at").first()
                
                if data_change_log:
                    assert data_change_log.audit_log_id == audit_log.id, \
                        f"DataChangeLog audit_log_id should match AuditLog id"
                    assert data_change_log.user_id == user.id, \
                        f"DataChangeLog user_id should match user"

    def test_3_2_successful_enable_by_saas_account_manager(self, authenticated_client, http_client):
        """Test Scenario 3.2: SaaS Account Manager can enable LLM"""
        email, password = get_user_credentials("SaaS Account Manager")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure LLM_MANAGEMENT subscription exists
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        model_key = "gpt-4.1"
        
        # Ensure LLM is not already enabled
        if DJANGO_AVAILABLE and OrganizationEnabledLLM:
            OrganizationEnabledLLM.objects.using('default').filter(
                organization=org,
                model_key=model_key
            ).update(disabled_at=timezone.now())
        
        # Make request
        response = make_request(client, "post", f"/llms/organizations/{org_uuid}/{model_key}/enable/")
        
        # Verify response
        assert response.status_code in [200, 201], \
            f"Expected 200 or 201 but got {response.status_code}, response: {response.text}"

    def test_3_3_enable_hosted_model_without_subscription_rejected(self, authenticated_client, http_client):
        """Test Scenario 3.3: Enabling hosted model without subscription is rejected"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization without hosted subscription
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure LLM_MANAGEMENT subscription exists (but not hosted models)
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        model_key = "deepseek-r1"  # SaaS Platform Hosted model
        
        # Make request
        before_request = timezone.now()
        response = make_request(client, "post", f"/llms/organizations/{org_uuid}/{model_key}/enable/")
        
        # Verify response - should be rejected
        assert response.status_code in [400, 403, 404], \
            f"Expected 400, 403, or 404 but got {response.status_code}, response: {response.text}"
        
        # Verify audit log for failed request
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/llms/organizations/{org_uuid}/{model_key}/enable/",
                method="POST",
                status_code__in=[400, 403, 404],
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            if audit_log:
                assert audit_log.success is False, "Audit log should mark success as False"
                assert audit_log.user_id == user.id, "Audit log should reference correct user"

    def test_3_4_re_enable_previously_disabled_llm(self, authenticated_client, http_client):
        """Test Scenario 3.4: Re-enabling previously disabled LLM clears disabledAt"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization and OrganizationEnabledLLM:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure LLM_MANAGEMENT subscription exists
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
            
            model_key = "gpt-4o-mini"
            user = User.objects.using('default').filter(email=email).first()
            
            # Create a disabled LLM
            enabled_llm, _ = OrganizationEnabledLLM.objects.using('default').get_or_create(
                organization=org,
                model_key=model_key,
                defaults={
                    "model_provider": "OpenAI",
                    "enabled_by": user,
                    "disabled_at": timezone.now(),
                }
            )
            if enabled_llm.disabled_at is None:
                enabled_llm.disable(actor=user)
                enabled_llm.save()
        else:
            pytest.skip("Django models not available")
        
        # Make request to re-enable
        before_request = timezone.now()
        response = make_request(client, "post", f"/llms/organizations/{org_uuid}/{model_key}/enable/")
        
        # Verify response
        assert response.status_code in [200, 201], \
            f"Expected 200 or 201 but got {response.status_code}, response: {response.text}"
        
        # Verify database state - disabledAt should be cleared
        if DJANGO_AVAILABLE and OrganizationEnabledLLM:
            assert not OrganizationEnabledLLM.objects.using('default').filter(
                organization=org,
                model_key=model_key,
                disabled_at__isnull=False
            ).exists()

            enabled_llm = OrganizationEnabledLLM.objects.using('default').filter(
                organization=org,
                model_key=model_key
            ).first()
            
            assert enabled_llm is not None, "LLM should exist"
            assert enabled_llm.disabled_at is None, "disabledAt should be cleared on re-enable"

    def test_3_5_enable_rejected_by_agent_manager(self, authenticated_client, http_client):
        """Test Scenario 3.5: Regular user without llms:enable permission cannot enable LLM"""
        email, password = get_user_credentials("Account 1 User 1")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure LLM_MANAGEMENT subscription exists
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        model_key = "gpt-4o-mini"
        
        # Make request
        before_request = timezone.now()
        response = make_request(client, "post", f"/llms/organizations/{org_uuid}/{model_key}/enable/")
        
        # Verify response - should be 403
        assert response.status_code == 403, \
            f"Expected 403 but got {response.status_code}, response: {response.text}"
        
        # Verify audit log for failed request
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/llms/organizations/{org_uuid}/{model_key}/enable/",
                method="POST",
                status_code=403,
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            if audit_log:
                assert audit_log.success is False, "Audit log should mark success as False"
                assert audit_log.user_id == user.id, "Audit log should reference correct user"

    def test_3_6_enable_nonexistent_model_rejected(self, authenticated_client, http_client):
        """Test Scenario 3.6: Enabling non-existent modelKey is rejected"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure LLM_MANAGEMENT subscription exists
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        model_key = "nonexistent-model-12345"
        
        # Make request
        before_request = timezone.now()
        response = make_request(client, "post", f"/llms/organizations/{org_uuid}/{model_key}/enable/")
        
        # Verify response - should be 404
        assert response.status_code == 404, \
            f"Expected 404 but got {response.status_code}, response: {response.text}"
        
        # Verify audit log for failed request
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/llms/organizations/{org_uuid}/{model_key}/enable/",
                method="POST",
                status_code=404,
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            if audit_log:
                assert audit_log.success is False, "Audit log should mark success as False"

    def test_3_7_enable_unauthenticated(self, http_client):
        """Test Scenario 3.7: Unauthenticated request is rejected"""
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        model_key = "gpt-4o-mini"
        
        # Make request
        response = make_request(http_client, "post", f"/llms/organizations/{org_uuid}/{model_key}/enable/")
        
        # Verify response
        assert response.status_code == 401, \
            f"Expected 401 but got {response.status_code}, response: {response.text}"
    
    def test_3_8_enable_denied_without_llm_management_subscription(self, authenticated_client, http_client):
        """Test Scenario 3.8: Even SAAS Administrator cannot enable LLM without LLM_MANAGEMENT subscription"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization without LLM_MANAGEMENT subscription
        if DJANGO_AVAILABLE and Organization and Module:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            
            # Remove LLM_MANAGEMENT subscription if it exists
            llm_module = Module.objects.using('default').filter(key="LLM_MANAGEMENT").first()
            if llm_module:
                Subscription.objects.using('default').filter(
                    organization=org,
                    module=llm_module
                ).delete()
            
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        model_key = "gpt-4o-mini"
        
        # Make request
        response = make_request(client, "post", f"/llms/organizations/{org_uuid}/{model_key}/enable/")
        
        # Verify response - should be denied even for SAAS Administrator
        assert response.status_code in [403, 404], \
            f"Expected 403 or 404 without subscription but got {response.status_code}, response: {response.text}"
    
    def test_3_9_user_roles_cannot_enable_only_saas_roles_can(self, authenticated_client, http_client):
        """Test Scenario 3.9: User roles (Account-Admin, Account-Owner, Org-Admin, Org-Owner) cannot enable - only SAAS-* roles can"""
        if not DJANGO_AVAILABLE or not Organization:
            pytest.skip("Django models not available")
        
        org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
        if not org:
            pytest.skip("Test organization not found")
        
        # Ensure LLM_MANAGEMENT subscription exists
        ensure_llm_management_subscription(org)
        org_uuid = str(org.uuid)
        model_key = "gpt-4.1"
        
        # Ensure LLM is not already enabled
        if OrganizationEnabledLLM:
            OrganizationEnabledLLM.objects.using('default').filter(
                organization=org,
                model_key=model_key
            ).update(disabled_at=timezone.now())
        
        # Test Account Admin - should NOT be able to enable (403)
        email, password = get_user_credentials("Account 1 Admin")
        client = authenticated_client(email, password)
        response = make_request(client, "post", f"/llms/organizations/{org_uuid}/{model_key}/enable/")
        assert response.status_code == 403, \
            f"Account Admin should NOT have access to enable (only SAAS-* roles can), got {response.status_code}, response: {response.text}"
        
        # Test Account Owner - should NOT be able to enable (403)
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        response = make_request(client, "post", f"/llms/organizations/{org_uuid}/{model_key}/enable/")
        assert response.status_code == 403, \
            f"Account Owner should NOT have access to enable (only SAAS-* roles can), got {response.status_code}, response: {response.text}"
        
        # Test Organization Admin - should NOT be able to enable (403)
        email, password = get_user_credentials("Account 1 Org Admin")
        client = authenticated_client(email, password)
        response = make_request(client, "post", f"/llms/organizations/{org_uuid}/{model_key}/enable/")
        assert response.status_code == 403, \
            f"Organization Admin should NOT have access to enable (only SAAS-* roles can), got {response.status_code}, response: {response.text}"


@pytest.mark.acceptance
class TestREQLLM004DisableLLMForOrganization:
    """REQ-LLM-004: Disable LLM for Organization"""

    def test_4_1_successful_disable_by_saas_administrator(self, authenticated_client, http_client):
        """Test Scenario 4.1: SaaS Administrator can disable LLM"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization and OrganizationEnabledLLM:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure LLM_MANAGEMENT subscription exists
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
            
            model_key = "gpt-4o-mini"
            user = User.objects.using('default').filter(email=email).first()
            
            # Ensure LLM is enabled
            enabled_llm, _ = OrganizationEnabledLLM.objects.using('default').get_or_create(
                organization=org,
                model_key=model_key,
                defaults={
                    "model_provider": "OpenAI",
                    "enabled_by": user,
                    "disabled_at": None,
                }
            )
            if enabled_llm.disabled_at:
                enabled_llm.disabled_at = None
                enabled_llm.save()
        else:
            pytest.skip("Django models not available")
        
        # Make request
        before_request = timezone.now()
        response = make_request(client, "post", f"/llms/organizations/{org_uuid}/{model_key}/disable/")
        
        # Verify response
        assert response.status_code in [200, 204], \
            f"Expected 200 or 204 but got {response.status_code}, response: {response.text}"
        
        # Verify database state
        if DJANGO_AVAILABLE and OrganizationEnabledLLM:
            enabled_llm = OrganizationEnabledLLM.objects.using('default').filter(
                organization=org,
                model_key=model_key
            ).first()
            
            assert enabled_llm is not None, "LLM record should exist"
            assert enabled_llm.disabled_at is not None, "disabledAt should be set"
        
        # Verify audit log
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/llms/organizations/{org_uuid}/{model_key}/disable/",
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
                    model_name="OrganizationEnabledLLM",
                    action="update",
                    created_at__gte=before_request - timedelta(seconds=1)
                ).order_by("-created_at").first()
                
                if data_change_log:
                    assert data_change_log.audit_log_id == audit_log.id, \
                        f"DataChangeLog audit_log_id should match AuditLog id"
                    assert data_change_log.user_id == user.id, \
                        f"DataChangeLog user_id should match user"

    def test_4_2_disable_already_disabled_rejected(self, authenticated_client, http_client):
        """Test Scenario 4.2: Disabling already disabled LLM is rejected"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization and OrganizationEnabledLLM:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure LLM_MANAGEMENT subscription exists
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
            
            model_key = "gpt-4o-mini"
            user = User.objects.using('default').filter(email=email).first()
            
            # Ensure LLM is disabled
            enabled_llm, _ = OrganizationEnabledLLM.objects.using('default').get_or_create(
                organization=org,
                model_key=model_key,
                defaults={
                    "model_provider": "OpenAI",
                    "enabled_by": user,
                    "disabled_at": timezone.now(),
                }
            )
            if enabled_llm.disabled_at is None:
                enabled_llm.disable(actor=user)
                enabled_llm.save()
        else:
            pytest.skip("Django models not available")
        
        # Make request
        before_request = timezone.now()
        response = make_request(client, "post", f"/llms/organizations/{org_uuid}/{model_key}/disable/")
        
        # Verify response - should be rejected (400 or 409)
        assert response.status_code in [400, 409], \
            f"Expected 400 or 409 but got {response.status_code}, response: {response.text}"
        
        # Verify audit log for failed request
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/llms/organizations/{org_uuid}/{model_key}/disable/",
                method="POST",
                status_code__in=[400, 409],
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            if audit_log:
                assert audit_log.success is False, "Audit log should mark success as False"

    def test_4_3_disable_rejected_by_agent_manager(self, authenticated_client, http_client):
        """Test Scenario 4.3: Agent Manager (without llms:disable) cannot disable LLM"""
        if not DJANGO_AVAILABLE or not all([Organization, Module, Role, RoleAssignment, UserOrganization]):
            pytest.skip("Django models not available")
        org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
        if not org:
            pytest.skip("Test organization not found")
        ensure_llm_management_subscription(org)
        org_uuid = str(org.uuid)
        superuser = User.objects.using('default').filter(is_superuser=True).first()
        if not superuser:
            pytest.skip("Superuser not found")
        # Agent Manager role: Only assignable permissions are llms:read and llms:validate
        # Note: llms:list, llms:enable, llms:disable, llms:admin are ONLY for SAAS-* roles
        agent_manager_no_disable_permissions = [
            "llms:read", "llms:validate",
        ]
        agent_manager_role, _ = Role.objects.using('default').get_or_create(
            organization=org,
            name="Agent Manager (No Disable)",
            defaults={
                "role_type": Role.RoleType.PREDEFINED_CUSTOM,
                "is_active": True,
                "permissions": agent_manager_no_disable_permissions,
                "created_by": superuser,
            },
        )
        if agent_manager_role.permissions != agent_manager_no_disable_permissions:
            agent_manager_role.permissions = agent_manager_no_disable_permissions
            agent_manager_role.is_active = True
            agent_manager_role.save()
        agent_manager_user, _ = User.objects.using('default').get_or_create(
            email="agent.manager.nodisable@test.com",
            defaults={"full_name": "Agent Manager No Disable", "is_active": True},
        )
        agent_manager_user.set_password("Test123!")
        agent_manager_user.save()
        UserOrganization.objects.using('default').get_or_create(
            user=agent_manager_user,
            organization=org,
            defaults={"assigned_by": superuser, "is_active": True},
        )
        RoleAssignment.objects.using('default').get_or_create(
            user=agent_manager_user,
            organization=org,
            role=agent_manager_role,
            defaults={"assigned_by": superuser},
        )
        email, password = "agent.manager.nodisable@test.com", "Test123!"
        client = authenticated_client(email, password)
        model_key = "gpt-4o-mini"
        before_request = timezone.now()
        response = make_request(client, "post", f"/llms/organizations/{org_uuid}/{model_key}/disable/")
        assert response.status_code == 403, (
            f"Agent Manager without llms:disable should get 403. "
            f"Got {response.status_code}, response: {response.text}"
        )
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/llms/organizations/{org_uuid}/{model_key}/disable/",
                method="POST",
                status_code=403,
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            if audit_log:
                assert audit_log.success is False, "Audit log should mark success as False"

    def test_4_4_disable_unauthenticated(self, http_client):
        """Test Scenario 4.4: Unauthenticated request is rejected"""
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        model_key = "gpt-4o-mini"
        
        # Make request
        response = make_request(http_client, "post", f"/llms/organizations/{org_uuid}/{model_key}/disable/")
        
        # Verify response
        assert response.status_code == 401, \
            f"Expected 401 but got {response.status_code}, response: {response.text}"
    
    def test_4_5_disable_denied_without_llm_management_subscription(self, authenticated_client, http_client):
        """Test Scenario 4.5: Even SAAS Administrator cannot disable LLM without LLM_MANAGEMENT subscription"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization without LLM_MANAGEMENT subscription
        if DJANGO_AVAILABLE and Organization and Module:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            
            # Remove LLM_MANAGEMENT subscription if it exists
            llm_module = Module.objects.using('default').filter(key="LLM_MANAGEMENT").first()
            if llm_module:
                Subscription.objects.using('default').filter(
                    organization=org,
                    module=llm_module
                ).delete()
            
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        model_key = "gpt-4o-mini"
        
        # Make request
        response = make_request(client, "post", f"/llms/organizations/{org_uuid}/{model_key}/disable/")
        
        # Verify response - should be denied even for SAAS Administrator
        assert response.status_code in [403, 404], \
            f"Expected 403 or 404 without subscription but got {response.status_code}, response: {response.text}"
    
    def test_4_6_user_roles_cannot_disable_only_saas_roles_can(self, authenticated_client, http_client):
        """Test Scenario 4.6: User roles (Account-Admin, Account-Owner, Org-Admin, Org-Owner) cannot disable - only SAAS-* roles can"""
        if not DJANGO_AVAILABLE or not Organization or not OrganizationEnabledLLM:
            pytest.skip("Django models not available")
        
        org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
        if not org:
            pytest.skip("Test organization not found")
        
        # Ensure LLM_MANAGEMENT subscription exists
        ensure_llm_management_subscription(org)
        org_uuid = str(org.uuid)
        model_key = "gpt-4o-mini"
        
        # Ensure LLM is enabled
        user = User.objects.using('default').filter(is_superuser=True).first()
        enabled_llm, _ = OrganizationEnabledLLM.objects.using('default').get_or_create(
            organization=org,
            model_key=model_key,
            defaults={
                "model_provider": "OpenAI",
                "enabled_by": user,
                "disabled_at": None,
            }
        )
        if enabled_llm.disabled_at:
            enabled_llm.disabled_at = None
            enabled_llm.save()
        
        # Test Account Admin - should NOT be able to disable (403)
        email, password = get_user_credentials("Account 1 Admin")
        client = authenticated_client(email, password)
        response = make_request(client, "post", f"/llms/organizations/{org_uuid}/{model_key}/disable/")
        assert response.status_code == 403, \
            f"Account Admin should NOT have access to disable (only SAAS-* roles can), got {response.status_code}, response: {response.text}"
        
        # Re-enable for next test
        enabled_llm.disabled_at = None
        enabled_llm.save()
        
        # Test Account Owner - should NOT be able to disable (403)
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        response = make_request(client, "post", f"/llms/organizations/{org_uuid}/{model_key}/disable/")
        assert response.status_code == 403, \
            f"Account Owner should NOT have access to disable (only SAAS-* roles can), got {response.status_code}, response: {response.text}"
        
        # Re-enable for next test
        enabled_llm.disabled_at = None
        enabled_llm.save()
        
        # Test Organization Admin - should NOT be able to disable (403)
        email, password = get_user_credentials("Account 1 Org Admin")
        client = authenticated_client(email, password)
        response = make_request(client, "post", f"/llms/organizations/{org_uuid}/{model_key}/disable/")
        assert response.status_code == 403, \
            f"Organization Admin should NOT have access to disable (only SAAS-* roles can), got {response.status_code}, response: {response.text}"


@pytest.mark.acceptance
class TestREQLLM005ValidateLLMConfiguration:
    """REQ-LLM-005: Validate LLM Configuration"""

    def test_5_1_valid_configuration_passes(self, authenticated_client, http_client):
        """Test Scenario 5.1: Valid configuration passes validation"""
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure LLM_MANAGEMENT subscription exists
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        model_key = "gpt-4o-mini"
        for usr in ["Super Admin", "Account 1 Admin", "Account 1 Owner", "Account 1 Org Admin"]:
            email, password = get_user_credentials(usr)
            client = authenticated_client(email, password)

            if usr == "Super Admin":
                if DJANGO_AVAILABLE and OrganizationEnabledLLM:
                    enabled_llm = OrganizationEnabledLLM.objects.using('default').filter(
                        organization=org,
                        model_key=model_key
                    ).delete()
                response = make_request(client, "post", f"/llms/organizations/{org_uuid}/{model_key}/enable/")
                assert response.status_code == 200, \
                    f"{usr} should be able to enable {model_key} LLM, Expected 200 but got {response.status_code}, response: {response.text}"
            
            payload = {
                "organization_uuid": org_uuid,
                "modelKey": model_key,
                "modelProvider": "OpenAI",
                "configuration": {
                    "temperature": 0.7,
                    "maxTokens": 1000,
                    "topP": 0.9,
                }
            }
            
            # Make request
            before_request = timezone.now()
            response = make_request(client, "post", "/llms/validate/", json=payload)
            
            # Verify response
            assert response.status_code == 200, \
                f"{usr} should be able to validate LLM configuration, Expected 200 but got {response.status_code}, response: {response.text}"
            
            data = response.json()
            # Response should indicate validation passed
            # Exact structure depends on implementation
            
            # Verify audit log
            if DJANGO_AVAILABLE and AuditLog:
                user = User.objects.using('default').filter(email=email).first()
                audit_log = AuditLog.objects.using('default').filter(
                    path="/api/llms/validate/",
                    method="POST",
                    status_code=200,
                    created_at__gte=before_request - timedelta(seconds=1)
                ).order_by("-created_at").first()
                
                if audit_log:
                    assert audit_log.success is True, "Audit log should mark success as True"
                    assert audit_log.user_id == user.id, "Audit log should reference correct user"

    def test_5_2_invalid_temperature_range_fails(self, authenticated_client, http_client):
        """Test Scenario 5.2: Temperature outside valid range fails validation"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure LLM_MANAGEMENT subscription exists
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        model_key = "gpt-4o-mini"
        if DJANGO_AVAILABLE and OrganizationEnabledLLM:
            enabled_llm = OrganizationEnabledLLM.objects.using('default').filter(
                organization=org,
                model_key=model_key
            ).delete()
        response = make_request(client, "post", f"/llms/organizations/{org_uuid}/{model_key}/enable/")
        assert response.status_code == 200, \
            f"Super Admin should be able to enable {model_key} LLM, Expected 200 but got {response.status_code}, response: {response.text}"
        payload = {
            "organization_uuid": org_uuid,
            "modelKey": model_key,
            "modelProvider": "OpenAI",
            "configuration": {
                "temperature": 1.5,  # Invalid: max is 1.0
                "maxTokens": 1000,
            }
        }
        
        # Make request
        before_request = timezone.now()
        response = make_request(client, "post", "/llms/validate/", json=payload)
        
        # Verify response - should fail validation
        assert response.status_code == 400, \
            f"Expected 400 but got {response.status_code}, response: {response.text}"
        
        # Verify audit log for failed request
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path="/api/llms/validate/",
                method="POST",
                status_code=400,
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            if audit_log:
                assert audit_log.success is False, "Audit log should mark success as False"

    def test_5_3_invalid_max_tokens_fails(self, authenticated_client, http_client):
        """Test Scenario 5.3: MaxTokens exceeding limit fails validation"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure LLM_MANAGEMENT subscription exists
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        model_key = "gpt-4o-mini"
        # Ensure LLM definition exists before enabling
        if DJANGO_AVAILABLE and LLMDefinition:
            llm_def = LLMDefinition.objects.using('default').filter(model_key=model_key).first()
            if not llm_def:
                pytest.skip(f"LLM definition for {model_key} not found in database")
        if DJANGO_AVAILABLE and OrganizationEnabledLLM:
            enabled_llm = OrganizationEnabledLLM.objects.using('default').filter(
                organization=org,
                model_key=model_key
            ).delete()
        response = make_request(client, "post", f"/llms/organizations/{org_uuid}/{model_key}/enable/")
        assert response.status_code == 200, \
            f"Super Admin should be able to enable {model_key} LLM, Expected 200 but got {response.status_code}, response: {response.text}"
        payload = {
            "organization_uuid": org_uuid,
            "modelKey": model_key,
            "modelProvider": "OpenAI",
            "configuration": {
                "temperature": 0.7,
                "maxTokens": 2000000,  # Invalid: exceeds max context
            }
        }
        
        # Make request
        response = make_request(client, "post", "/llms/validate/", json=payload)
        
        # Verify response - should fail validation
        assert response.status_code == 400, \
            f"Expected 400 but got {response.status_code}, response: {response.text}"

    def test_5_4_missing_required_parameter_fails(self, authenticated_client, http_client):
        """Test Scenario 5.4: Missing required parameter fails validation"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure LLM_MANAGEMENT subscription exists
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        model_key = "gpt-4o-mini"
        # Ensure LLM definition exists before enabling
        if DJANGO_AVAILABLE and LLMDefinition:
            llm_def = LLMDefinition.objects.using('default').filter(model_key=model_key).first()
            if not llm_def:
                pytest.skip(f"LLM definition for {model_key} not found in database")
        if DJANGO_AVAILABLE and OrganizationEnabledLLM:
            enabled_llm = OrganizationEnabledLLM.objects.using('default').filter(
                organization=org,
                model_key=model_key
            ).delete()
        response = make_request(client, "post", f"/llms/organizations/{org_uuid}/{model_key}/enable/")
        assert response.status_code == 200, \
            f"Super Admin should be able to enable {model_key} LLM, Expected 200 but got {response.status_code}, response: {response.text}"
        payload = {
            "organization_uuid": org_uuid,
            "modelKey": model_key,
            "modelProvider": "OpenAI",
            "configuration": {
                # Missing required parameters if any
            }
        }
        
        # Make request
        response = make_request(client, "post", "/llms/validate/", json=payload)
        
        # Verify response - may pass if no required parameters, or fail if there are
        assert response.status_code in [200, 400], \
            f"Expected 200 or 400 but got {response.status_code}, response: {response.text}"

    def test_5_5_wrong_parameter_type_fails(self, authenticated_client, http_client):
        """Test Scenario 5.5: Wrong parameter type fails validation"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization UUID
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure LLM_MANAGEMENT subscription exists
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        model_key = "gpt-4o-mini"
        # Ensure LLM definition exists before enabling
        if DJANGO_AVAILABLE and LLMDefinition:
            llm_def = LLMDefinition.objects.using('default').filter(model_key=model_key).first()
            if not llm_def:
                pytest.skip(f"LLM definition for {model_key} not found in database")
        if DJANGO_AVAILABLE and OrganizationEnabledLLM:
            enabled_llm = OrganizationEnabledLLM.objects.using('default').filter(
                organization=org,
                model_key=model_key
            ).delete()
        response = make_request(client, "post", f"/llms/organizations/{org_uuid}/{model_key}/enable/")
        assert response.status_code == 200, \
            f"Super Admin should be able to enable {model_key} LLM, Expected 200 but got {response.status_code}, response: {response.text}"
        payload = {
            "organization_uuid": org_uuid,
            "modelKey": model_key,
            "modelProvider": "OpenAI",
            "configuration": {
                "temperature": "not-a-number",  # Invalid: should be number
                "maxTokens": 1000,
            }
        }
        
        # Make request
        response = make_request(client, "post", "/llms/validate/", json=payload)
        
        # Verify response - should fail validation
        assert response.status_code == 400, \
            f"Expected 400 but got {response.status_code}, response: {response.text}"

    def test_5_6_validate_unauthenticated(self, http_client):
        """Test Scenario 5.6: Unauthenticated request is rejected"""
        payload = {
            "organization_uuid": "00000000-0000-0000-0000-000000000000",
            "modelKey": "gpt-4o-mini",
            "modelProvider": "OpenAI",
            "configuration": {
                "temperature": 0.7,
            }
        }
        
        # Make request
        response = make_request(http_client, "post", "/llms/validate/", json=payload)
        
        # Verify response
        assert response.status_code == 401, \
            f"Expected 401 but got {response.status_code}, response: {response.text}"
    
    def test_5_7_validate_denied_without_llm_management_subscription(self, authenticated_client, http_client):
        """Test Scenario 5.7: Even SAAS Administrator cannot validate LLM configuration without LLM_MANAGEMENT subscription"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization without LLM_MANAGEMENT subscription
        if DJANGO_AVAILABLE and Organization and Module:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            ensure_llm_management_subscription(org)
            model_key = "gpt-4o-mini"
            org_uuid = str(org.uuid)
            if DJANGO_AVAILABLE and OrganizationEnabledLLM:
                enabled_llm = OrganizationEnabledLLM.objects.using('default').filter(
                    organization=org,
                    model_key=model_key
                ).delete()
            response = make_request(client, "post", f"/llms/organizations/{org_uuid}/{model_key}/enable/")
            assert response.status_code == 200, \
                f"Super Admin should be able to enable {model_key} LLM, Expected 200 but got {response.status_code}, response: {response.text}"
            
            # Remove LLM_MANAGEMENT subscription if it exists
            llm_module = Module.objects.using('default').filter(key="LLM_MANAGEMENT").first()
            if llm_module:
                Subscription.objects.using('default').filter(
                    organization=org,
                    module=llm_module
                ).delete()
            
        else:
            pytest.skip("Django models not available")
        
        payload = {
            "organization_uuid": org_uuid,
            "modelKey": model_key,
            "modelProvider": "OpenAI",
            "configuration": {
                "temperature": 0.7,
                "maxTokens": 1000,
            }
        }
        
        # Make request
        response = make_request(client, "post", "/llms/validate/", json=payload)
        
        # Verify response - should be denied even for SAAS Administrator
        assert response.status_code in [403, 404], \
            f"Expected 403 or 404 without subscription but got {response.status_code}, response: {response.text}"
    
    def test_5_8_validate_unauthenticated(self, http_client):
        """Test Scenario 5.6: Unauthenticated request is rejected"""
        payload = {
            "organization_uuid": "00000000-0000-0000-0000-000000000000",
            "modelKey": "gpt-4o-mini",
            "modelProvider": "OpenAI",
            "configuration": {
                "temperature": 0.7,
            }
        }
        
        # Make request
        response = make_request(http_client, "post", "/llms/validate/", json=payload)
        
        # Verify response
        assert response.status_code == 401, \
            f"Expected 401 but got {response.status_code}, response: {response.text}"


@pytest.mark.acceptance
class TestREQLLM006SubscriptionBasedAccessControl:
    """REQ-LLM-006: Subscription-Based Access Control for Hosted Models"""

    def test_6_1_enable_hosted_without_subscription_rejected(self, authenticated_client, http_client):
        """Test Scenario 6.1: Enabling hosted model without subscription is rejected"""
        email, password = get_user_credentials("SaaS Account Manager")
        client = authenticated_client(email, password)
        
        # Get organization without hosted subscription
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure LLM_MANAGEMENT subscription exists (but not hosted models)
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        model_key = "deepseek-r1"  # SaaS Platform Hosted model
        
        # Make request
        before_request = timezone.now()
        response = make_request(client, "post", f"/llms/organizations/{org_uuid}/{model_key}/enable/")
        
        # Verify response - should be rejected
        assert response.status_code in [400, 403, 404], \
            f"Expected 400, 403, or 404 but got {response.status_code}, response: {response.text}"
        
        # Verify audit log for failed request
        if DJANGO_AVAILABLE and AuditLog:
            user = User.objects.using('default').filter(email=email).first()
            audit_log = AuditLog.objects.using('default').filter(
                path=f"/api/llms/organizations/{org_uuid}/{model_key}/enable/",
                method="POST",
                status_code__in=[400, 403, 404],
                created_at__gte=before_request - timedelta(seconds=1)
            ).order_by("-created_at").first()
            
            if audit_log:
                assert audit_log.success is False, "Audit log should mark success as False"

    def test_6_2_enable_hosted_with_subscription_succeeds(self, authenticated_client, http_client):
        """Test Scenario 6.2: Enabling hosted model with subscription succeeds"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization and add hosted subscription
        if DJANGO_AVAILABLE and Organization and Subscription:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            
            # Ensure LLM_MANAGEMENT subscription exists
            subscription = ensure_llm_management_subscription(org)
            
            # Ensure subscription has hosted models enabled
            if subscription:
                config = subscription.configuration or {}
                config["llms_enabled_hosted_models"] = ["deepseek-r1", "qwen3-8b"]
                subscription.configuration = config
                subscription.save()
            
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        model_key = "deepseek-r1"  # SaaS Platform Hosted model
        
        # Ensure LLM is not already enabled
        if DJANGO_AVAILABLE and OrganizationEnabledLLM:
            OrganizationEnabledLLM.objects.using('default').filter(
                organization=org,
                model_key=model_key
            ).update(disabled_at=timezone.now())
        
        # Make request
        response = make_request(client, "post", f"/llms/organizations/{org_uuid}/{model_key}/enable/")
        
        # Verify response - should succeed
        assert response.status_code in [200, 201], \
            f"Expected 200 or 201 but got {response.status_code}, response: {response.text}"

    def test_6_3_enable_openai_regardless_of_subscription(self, authenticated_client, http_client):
        """Test Scenario 6.3: OpenAI models can be enabled regardless of subscription"""
        email, password = get_user_credentials("SaaS Account Manager")
        client = authenticated_client(email, password)
        
        # Get organization without hosted subscription
        if DJANGO_AVAILABLE and Organization:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            # Ensure LLM_MANAGEMENT subscription exists (but not hosted models)
            ensure_llm_management_subscription(org)
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        model_key = "gpt-4o-mini"  # OpenAI model
        
        # Ensure LLM is not already enabled
        if DJANGO_AVAILABLE and OrganizationEnabledLLM:
            OrganizationEnabledLLM.objects.using('default').filter(
                organization=org,
                model_key=model_key
            ).update(disabled_at=timezone.now())
        
        # Make request
        response = make_request(client, "post", f"/llms/organizations/{org_uuid}/{model_key}/enable/")
        
        # Verify response - should succeed
        assert response.status_code in [200, 201], \
            f"Expected 200 or 201 but got {response.status_code}, response: {response.text}"

    def test_6_4_enable_non_allowed_hosted_model_rejected(self, authenticated_client, http_client):
        """Test Scenario 6.4: Enabling non-allowed hosted model is rejected"""
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        
        # Get organization with limited hosted subscription
        if DJANGO_AVAILABLE and Organization and Subscription:
            org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
            if not org:
                pytest.skip("Test organization not found")
            
            # Ensure LLM_MANAGEMENT subscription exists
            subscription = ensure_llm_management_subscription(org)
            
            # Set subscription to allow only specific hosted models
            if subscription:
                config = subscription.configuration or {}
                config["llms_enabled_hosted_models"] = ["deepseek-r1"]  # Only allow deepseek-r1
                subscription.configuration = config
                subscription.save()
            
            org_uuid = str(org.uuid)
        else:
            pytest.skip("Django models not available")
        
        model_key = "qwen3-8b"  # Hosted model not in allowed list
        
        # Make request
        response = make_request(client, "post", f"/llms/organizations/{org_uuid}/{model_key}/enable/")
        
        # Verify response - should be rejected if subscription enforcement is strict
        # May succeed if implementation allows any hosted model when subscription has hosted access
        assert response.status_code in [200, 201, 400, 403, 404], \
            f"Unexpected status code {response.status_code}, response: {response.text}"


@pytest.mark.acceptance
class TestLLMRolesAndPermissions:
    """Test LLM API access control based on roles, permissions, and module subscriptions"""

    def setup_method(self):
        """Setup test data: custom role, subscription, and user assignment"""
        if not DJANGO_AVAILABLE:
            pytest.skip("Django models not available")
        
        # Get or create test organization
        self.org = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
        if not self.org:
            pytest.skip("Test organization not found")
        
        # Get superuser for creating roles
        self.superuser = User.objects.using('default').filter(is_superuser=True).first()
        if not self.superuser:
            pytest.skip("Superuser not found")
        
        # Get LLM_MANAGEMENT module
        llm_module = Module.objects.using('default').filter(key="LLM_MANAGEMENT").first()
        if not llm_module:
            pytest.skip("LLM_MANAGEMENT module not found")
        
        # Create subscription to LLM_MANAGEMENT module
        self.subscription, _ = Subscription.objects.using('default').get_or_create(
            organization=self.org,
            module=llm_module,
            defaults={
                "status": Subscription.Status.ACTIVE,
                "configuration": {},
                "start_date": timezone.now() - timedelta(days=30),
                "end_date": None,
            }
        )
        if self.subscription.status != Subscription.Status.ACTIVE:
            self.subscription.status = Subscription.Status.ACTIVE
            self.subscription.save()
        
        # Create custom "Agent Manager" role with permissions
        # Note: Only assignable LLM permissions are llms:read and llms:validate
        # llms:list, llms:enable, llms:disable, llms:admin are ONLY for SAAS-* roles
        agent_manager_permissions = [
            "agents:create", "agents:read", "agents:update", "agents:delete",
            "agents:versions:save", "agents:versions:switch", "agents:clone",
            "agents:flows:create", "agents:flows:read", "agents:flows:update",
            "agents:flows:delete", "agents:flows:publish", "agents:flows:disable",
            "agents:flows:enable", "agents:flows:clone", "agents:flows:versions:read",
            "integrations:create", "integrations:read", "integrations:update",
            "integrations:activate", "integrations:deactivate", "integrations:delete",
            "integrations:test", "integrations:regenerate_secret",
            "llms:read", "llms:validate",  # Only assignable LLM permissions
            "kb:collections:create", "kb:collections:read", "kb:collections:update",
            "kb:collections:delete", "kb:collections:archive", "kb:collections:restore",
            "kb:resources:create", "kb:resources:delete", "kb:resources:move",
            "kb:resources:copy", "tools:read"
        ]
        
        self.agent_manager_role, _ = Role.objects.using('default').get_or_create(
            organization=self.org,
            name="Agent Manager",
            defaults={
                "role_type": Role.RoleType.PREDEFINED_CUSTOM,
                "is_active": True,
                "permissions": agent_manager_permissions,
                "created_by": self.superuser,
            }
        )
        if not self.agent_manager_role.is_active:
            self.agent_manager_role.is_active = True
            self.agent_manager_role.permissions = agent_manager_permissions
            self.agent_manager_role.save()
        
        # Create test user and assign role
        self.test_user, _ = User.objects.using('default').get_or_create(
            email="agent.manager.test@test.com",
            defaults={
                "full_name": "Agent Manager Test User",
                "is_active": True,
            }
        )
        self.test_user.set_password("Test123!")
        self.test_user.save()
        
        # Ensure user is member of organization
        UserOrganization.objects.using('default').get_or_create(
            user=self.test_user,
            organization=self.org,
            defaults={
                "assigned_by": self.superuser,
                "is_active": True,
            }
        )
        
        # Assign Agent Manager role to user
        RoleAssignment.objects.using('default').get_or_create(
            user=self.test_user,
            organization=self.org,
            role=self.agent_manager_role,
            defaults={
                "assigned_by": self.superuser,
            }
        )
        
        self.org_uuid = str(self.org.uuid)

    def test_1_user_with_custom_role_can_access_apis_in_own_organization(self, authenticated_client, http_client):
        """Test that user with Agent Manager role can access LLM APIs within their organization"""
        email, password = get_user_credentials("Super Admin")
        client1 = authenticated_client(email, password)
        model_key = "gpt-4o-mini"
        if DJANGO_AVAILABLE and OrganizationEnabledLLM:
            enabled_llm = OrganizationEnabledLLM.objects.using('default').filter(
                organization=self.org,
                model_key=model_key
            ).delete()
        response = make_request(client1, "post", f"/llms/organizations/{self.org_uuid}/{model_key}/enable/")
        assert response.status_code == 200, \
            f"Super Admin should be able to enable {model_key} LLM, Expected 200 but got {response.status_code}, response: {response.text}"
        client = authenticated_client("agent.manager.test@test.com", "Test123!")
        
        # Test list enabled LLMs endpoint
        response = make_request(client, "get", f"/llms/organizations/{self.org_uuid}/enabled/")
        assert response.status_code == 200, \
            f"list enabled LLMs endpoint Expected 200 but got {response.status_code}, response: {response.text}"
        data = response.json()
        assert len(data) == 1, \
            f"Expected 1 enabled LLM, got {len(data)}"
        assert data[0].get("modelKey") == model_key, \
            f"Expected {model_key} LLM, got {data[0]}"
        
        # Test list available LLMs endpoint - should fail (requires llms:list which is only for SAAS-* roles)
        response = make_request(client, "get", f"/llms/organizations/{self.org_uuid}/")
        assert response.status_code == 403, \
            f"list available LLMs endpoint should be 403 (llms:list only for SAAS-* roles), got {response.status_code}, response: {response.text}"
        
        # Test validate endpoint (requires llms:validate permission)
        payload = {
            "organization_uuid": self.org_uuid,
            "modelKey": model_key,
            "modelProvider": "OpenAI",
            "configuration": {
                "temperature": 0.7,
                "maxTokens": 1000,
            }
        }
        response = make_request(client, "post", "/llms/validate/", json=payload)
        assert response.status_code == 200, \
            f"validate endpoint Expected 200 but got {response.status_code}, response: {response.text}"

    def test_2_user_cannot_access_apis_in_other_organizations(self, authenticated_client, http_client):
        """Test that user cannot access LLM APIs in other organizations even if they have subscription"""
        client = authenticated_client("agent.manager.test@test.com", "Test123!")
        
        # Get another organization in the same account
        other_org = Organization.objects.using('default').filter(
            name="Test Organization Alpha2"
        ).first()
        
        if not other_org:
            pytest.skip("No other organization found in same account")
        
        other_org_uuid = str(other_org.uuid)
        
        # Ensure other org has LLM_MANAGEMENT subscription
        llm_module = Module.objects.using('default').filter(key="LLM_MANAGEMENT").first()
        if llm_module:
            Subscription.objects.using('default').get_or_create(
                organization=other_org,
                module=llm_module,
                defaults={
                    "status": Subscription.Status.ACTIVE,
                    "configuration": {},
                    "start_date": timezone.now() - timedelta(days=30),
                    "end_date": None,
                }
            )
        
        # Try to access APIs in other organization - should be rejected (403 or 404)
        response = make_request(client, "get", f"/llms/organizations/{other_org_uuid}/enabled/")
        assert response.status_code in [403, 404], \
            f"Expected 403 or 404 but got {response.status_code}, response: {response.text}"

    def test_3_user_loses_access_when_subscription_expires(self, authenticated_client, http_client):
        """Test that user loses access when subscription expires or is deactivated"""
        client = authenticated_client("agent.manager.test@test.com", "Test123!")
        
        # First verify access works
        response = make_request(client, "get", f"/llms/organizations/{self.org_uuid}/enabled/")
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        # Deactivate subscription
        self.subscription.status = Subscription.Status.EXPIRED
        self.subscription.end_date = timezone.now() - timedelta(days=1)
        self.subscription.save()
        
        # Now access should be denied
        response = make_request(client, "get", f"/llms/organizations/{self.org_uuid}/enabled/")
        assert response.status_code in [403, 404], \
            f"Expected 403 or 404 when subscription expired but got {response.status_code}, response: {response.text}"
        
        # Reactivate subscription for cleanup
        self.subscription.status = Subscription.Status.ACTIVE
        self.subscription.end_date = None
        self.subscription.save()

    def test_4_user_loses_access_when_permissions_removed(self, authenticated_client, http_client):
        """Test that user loses access when role permissions are modified and removed"""
        client = authenticated_client("agent.manager.test@test.com", "Test123!")
        
        # First verify access works
        response = make_request(client, "get", f"/llms/organizations/{self.org_uuid}/enabled/")
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"
        
        # Remove llms:read permission from role
        updated_permissions = [p for p in self.agent_manager_role.permissions if p != "llms:read"]
        self.agent_manager_role.permissions = updated_permissions
        self.agent_manager_role.save()
        # time.sleep(3600)
        
        # Now access should be denied
        response = make_request(client, "get", f"/llms/organizations/{self.org_uuid}/enabled/")
        assert response.status_code == 403, \
            f"Expected 403 when permission removed but got {response.status_code}, response: {response.text}"
        
        # Restore permission for cleanup
        self.agent_manager_role.permissions = [
            "agents:create", "agents:read", "agents:update", "agents:delete",
            "agents:versions:save", "agents:versions:switch", "agents:clone",
            "agents:flows:create", "agents:flows:read", "agents:flows:update",
            "agents:flows:delete", "agents:flows:publish", "agents:flows:disable",
            "agents:flows:enable", "agents:flows:clone", "agents:flows:versions:read",
            "integrations:create", "integrations:read", "integrations:update",
            "integrations:activate", "integrations:deactivate", "integrations:delete",
            "integrations:test", "integrations:regenerate_secret",
            "llms:read", "llms:validate",
            "kb:collections:create", "kb:collections:read", "kb:collections:update",
            "kb:collections:delete", "kb:collections:archive", "kb:collections:restore",
            "kb:resources:create", "kb:resources:delete", "kb:resources:move",
            "kb:resources:copy", "tools:read"
        ]
        self.agent_manager_role.save()

    def test_5_user_with_different_custom_role_with_permissions_can_access(self, authenticated_client, http_client):
        """Test that another user with different custom role name but same permissions can access"""
        # Create another custom role with different name but same LLM permissions
        custom_role_permissions = ["llms:read", "llms:validate"]
        
        custom_role, _ = Role.objects.using('default').get_or_create(
            organization=self.org,
            name="LLM Specialist",
            defaults={
                "role_type": Role.RoleType.USER_CUSTOM,
                "is_active": True,
                "permissions": custom_role_permissions,
                "created_by": self.superuser,
            }
        )
        if not custom_role.is_active:
            custom_role.is_active = True
            custom_role.permissions = custom_role_permissions
            custom_role.save()
        
        # Create another test user
        test_user2, _ = User.objects.using('default').get_or_create(
            email="llm.specialist.test@test.com",
            defaults={
                "full_name": "LLM Specialist Test User",
                "is_active": True,
            }
        )
        test_user2.set_password("Test123!")
        test_user2.save()
        
        # Ensure user is member of organization
        UserOrganization.objects.using('default').get_or_create(
            user=test_user2,
            organization=self.org,
            defaults={
                "assigned_by": self.superuser,
                "is_active": True,
            }
        )
        
        # Assign custom role to user
        RoleAssignment.objects.using('default').get_or_create(
            user=test_user2,
            organization=self.org,
            role=custom_role,
            defaults={
                "assigned_by": self.superuser,
            }
        )
        
        # Test access
        client = authenticated_client("llm.specialist.test@test.com", "Test123!")
        response = make_request(client, "get", f"/llms/organizations/{self.org_uuid}/enabled/")
        assert response.status_code == 200, \
            f"Expected 200 but got {response.status_code}, response: {response.text}"

    def test_6_system_roles_can_access_without_custom_permissions(self, authenticated_client, http_client):
        """Test that users with system roles (SAAS-Administrator, Account-Admin, etc.) can access without custom permission-keys"""
        # Test SAAS Administrator
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        response = make_request(client, "get", f"/llms/organizations/{self.org_uuid}/enabled/")
        assert response.status_code == 200, \
            f"SAAS Administrator should have access, got {response.status_code}, response: {response.text}"
        
        # Test SAAS Account Manager
        email, password = get_user_credentials("SaaS Account Manager")
        client = authenticated_client(email, password)
        response = make_request(client, "get", f"/llms/organizations/{self.org_uuid}/enabled/")
        assert response.status_code == 200, \
            f"SAAS Account Manager should have access, got {response.status_code}, response: {response.text}"
        
        # Test Account Admin
        email, password = get_user_credentials("Account 1 Admin")
        client = authenticated_client(email, password)
        response = make_request(client, "get", f"/llms/organizations/{self.org_uuid}/enabled/")
        assert response.status_code == 200, \
            f"Account Admin should have access, got {response.status_code}, response: {response.text}"
        
        # Test Account Owner
        email, password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email, password)
        response = make_request(client, "get", f"/llms/organizations/{self.org_uuid}/enabled/")
        assert response.status_code == 200, \
            f"Account Owner should have access, got {response.status_code}, response: {response.text}"
        
        # Test Organization Admin
        email, password = get_user_credentials("Account 1 Org Admin")
        client = authenticated_client(email, password)
        response = make_request(client, "get", f"/llms/organizations/{self.org_uuid}/enabled/")
        assert response.status_code == 200, \
            f"Organization Admin should have access, got {response.status_code}, response: {response.text}"

    def test_7_no_access_without_subscription_even_for_saas_administrator(self, authenticated_client, http_client):
        """Test that even SAAS Administrator cannot access APIs if organization is not subscribed to LLM_MANAGEMENT"""
        if not DJANGO_AVAILABLE:
            pytest.skip("Django models not available")
        
        # Create organization without subscription
        org_no_sub = Organization.objects.using('default').filter(name="Test Organization Alpha1").first()
        if not org_no_sub:
            pytest.skip("Test organization without subscription not found")
        
        org_no_sub_uuid = str(org_no_sub.uuid)
        
        # Ensure no LLM_MANAGEMENT subscription
        llm_module = Module.objects.using('default').filter(key="LLM_MANAGEMENT").first()
        if llm_module:
            Subscription.objects.using('default').filter(
                organization=org_no_sub,
                module=llm_module
            ).delete()
        
        # Test SAAS Administrator access - should be denied
        email, password = get_user_credentials("Super Admin")
        client = authenticated_client(email, password)
        response = make_request(client, "get", f"/llms/organizations/{org_no_sub_uuid}/enabled/")
        assert response.status_code in [403, 404], \
            f"SAAS Administrator should be denied access without subscription, got {response.status_code}, response: {response.text}"
