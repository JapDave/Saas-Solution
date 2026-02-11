import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.agents.models import OrganizationEnabledLLM
from apps.llms.models import LLMDefinition
from apps.organizations.tests.factories import OrganizationFactory
from apps.products.models import Module
from apps.roles.constants import (
    LLM_PERMISSION_KEYS,
    ROLE_SAAS_ADMINISTRATOR,
    ROLE_SAAS_ACCOUNT_MANAGER,
    ROLE_AGENT_MANAGER,
)
from apps.roles.models import Role, RoleAssignment
from apps.subscriptions.models import Subscription
from apps.users.models import UserOrganization
from apps.users.tests.factories import UserFactory


@pytest.fixture
def llm_client(db):
    organization = OrganizationFactory()
    user = UserFactory()
    # seed definitions in DB
    LLMDefinition.objects.create(
        model_key="gpt-4o-mini",
        model_provider="OpenAI",
        display_name="GPT-4o-mini",
        description="",
        model_configuration={"temperature": {"type": "number", "required": False, "validation": {"min": 0, "max": 1}},
                             "maxTokens": {"type": "number", "required": False, "validation": {"min": 1, "max": 1000000}}},
        supported_modalities=["text"],
        max_context_tokens=128000,
    )
    LLMDefinition.objects.create(
        model_key="gpt-4.1",
        model_provider="OpenAI",
        display_name="GPT-4.1",
        description="",
        model_configuration={"temperature": {"type": "number", "required": False, "validation": {"min": 0, "max": 1}}},
        supported_modalities=["text"],
        max_context_tokens=128000,
    )
    UserOrganization.objects.create(
        user=user,
        organization=organization,
        permission_keys=list(LLM_PERMISSION_KEYS),
        assigned_by=user,
    )
    saas_role, _ = Role.objects.get_or_create(
        organization=None,
        name=ROLE_SAAS_ADMINISTRATOR,
        defaults={
            "description": "System role for tests",
            "permissions": list(LLM_PERMISSION_KEYS),
            "role_type": Role.RoleType.SYSTEM,
            "created_by": user,
        },
    )
    RoleAssignment.objects.get_or_create(
        user=user,
        role=saas_role,
        organization=None,
        defaults={"assigned_by": user},
    )
    client = APIClient()
    client.force_authenticate(user=user)
    module, _ = Module.objects.get_or_create(
        key="LLM_MANAGEMENT",
        defaults={
            "code": "LLM",
            "name": "LLM Management",
            "description": "tests",
            "subscribable": True,
        },
    )
    Subscription.objects.update_or_create(
        organization=organization,
        module=module,
        defaults={
            "status": Subscription.Status.ACTIVE,
            "start_date": timezone.now(),
            "configuration": {"llms.max_enabled": 1},
        },
    )
    return organization, user, client


def _seed_llm_definitions():
    if LLMDefinition.objects.filter(model_key="gpt-4o-mini").exists():
        return
    LLMDefinition.objects.create(
        model_key="gpt-4o-mini",
        model_provider="OpenAI",
        display_name="GPT-4o-mini",
        description="",
        model_configuration={"temperature": {"type": "number", "required": False, "validation": {"min": 0, "max": 1}}},
        supported_modalities=["text"],
        max_context_tokens=128000,
    )


def _ensure_llm_module(exposed_permissions=None):
    module, _ = Module.objects.get_or_create(
        key="LLM_MANAGEMENT",
        defaults={
            "code": "LLM",
            "name": "LLM Management",
            "description": "tests",
            "subscribable": True,
        },
    )
    if exposed_permissions is not None:
        module.exposed_permissions = list(exposed_permissions)
        module.save(update_fields=["exposed_permissions", "updated_at"])
    return module


def _create_active_subscription(organization, module):
    Subscription.objects.update_or_create(
        organization=organization,
        module=module,
        defaults={
            "status": Subscription.Status.ACTIVE,
            "start_date": timezone.now(),
            "configuration": {"llms.max_enabled": 5},
        },
    )


@pytest.mark.django_db
def test_list_definitions(llm_client):
    organization, _, client = llm_client
    url = reverse("organization-llms-available", kwargs={"organization_uuid": organization.uuid})
    response = client.get(url)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()


@pytest.mark.django_db
def test_enable_llm(llm_client):
    organization, user, client = llm_client
    enable_url = reverse(
        "organization-llms-enable",
        kwargs={"organization_uuid": organization.uuid, "model_key": "gpt-4o-mini"},
    )
    response = client.post(enable_url)
    assert response.status_code == status.HTTP_200_OK
    assert OrganizationEnabledLLM.objects.filter(organization=organization, model_key="gpt-4o-mini").exists()


@pytest.mark.django_db
def test_enable_limit_enforced(llm_client):
    organization, user, client = llm_client
    first = reverse(
        "organization-llms-enable",
        kwargs={"organization_uuid": organization.uuid, "model_key": "gpt-4o-mini"},
    )
    assert client.post(first).status_code == status.HTTP_200_OK
    second = reverse(
        "organization-llms-enable",
        kwargs={"organization_uuid": organization.uuid, "model_key": "gpt-4.1"},
    )
    response = client.post(second)
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["code"] == "MAX_LLMS_EXCEEDED"


@pytest.mark.django_db
def test_validate_configuration(llm_client):
    organization, _, client = llm_client
    enable_url = reverse(
        "organization-llms-enable",
        kwargs={"organization_uuid": organization.uuid, "model_key": "gpt-4o-mini"},
    )
    client.post(enable_url)
    url = reverse("llm-validate")
    payload = {
        "organization_uuid": str(organization.uuid),
        "modelKey": "gpt-4o-mini",
        "modelProvider": "OpenAI",
        "configuration": {"temperature": 0.2, "maxTokens": 500},
    }
    response = client.post(url, payload, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert "modelKey" in response.json()


@pytest.mark.django_db
def test_subscription_required_even_for_saas_admin(db):
    org = OrganizationFactory()
    user = UserFactory()
    _seed_llm_definitions()
    saas_role, _ = Role.objects.get_or_create(
        organization=None,
        name=ROLE_SAAS_ADMINISTRATOR,
        defaults={
            "description": "System role for tests",
            "permissions": list(LLM_PERMISSION_KEYS),
            "role_type": Role.RoleType.SYSTEM,
            "created_by": user,
        },
    )
    RoleAssignment.objects.get_or_create(user=user, role=saas_role, organization=None, defaults={"assigned_by": user})
    client = APIClient()
    client.force_authenticate(user=user)
    url = reverse("organization-llms-available", kwargs={"organization_uuid": org.uuid})
    response = client.get(url)
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_saas_account_manager_assigned_can_list(db):
    org = OrganizationFactory()
    user = UserFactory()
    _seed_llm_definitions()
    _ensure_llm_module(exposed_permissions=list(LLM_PERMISSION_KEYS))
    _create_active_subscription(org, Module.objects.get(key="LLM_MANAGEMENT"))
    saas_mgr_role, _ = Role.objects.get_or_create(
        organization=None,
        name=ROLE_SAAS_ACCOUNT_MANAGER,
        defaults={
            "description": "System role for tests",
            "permissions": list(LLM_PERMISSION_KEYS),
            "role_type": Role.RoleType.SYSTEM,
            "created_by": user,
        },
    )
    RoleAssignment.objects.get_or_create(user=user, role=saas_mgr_role, organization=None, defaults={"assigned_by": user})
    user.user_preferences = {"assigned_account_ids": [org.account_id]}
    user.save(update_fields=["user_preferences", "updated_at"])
    client = APIClient()
    client.force_authenticate(user=user)
    url = reverse("organization-llms-available", kwargs={"organization_uuid": org.uuid})
    response = client.get(url)
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_account_owner_without_membership_can_access(db):
    org = OrganizationFactory()
    user = UserFactory()
    org.account.created_by = user
    org.account.save(update_fields=["created_by", "updated_at"])
    _seed_llm_definitions()
    _ensure_llm_module(exposed_permissions=list(LLM_PERMISSION_KEYS))
    _create_active_subscription(org, Module.objects.get(key="LLM_MANAGEMENT"))
    client = APIClient()
    client.force_authenticate(user=user)
    url = reverse("organization-llms-list", kwargs={"organization_uuid": org.uuid})
    response = client.get(url)
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_org_owner_without_membership_can_access(db):
    org = OrganizationFactory()
    user = UserFactory()
    org.created_by = user
    org.save(update_fields=["created_by", "updated_at"])
    _seed_llm_definitions()
    _ensure_llm_module(exposed_permissions=list(LLM_PERMISSION_KEYS))
    _create_active_subscription(org, Module.objects.get(key="LLM_MANAGEMENT"))
    client = APIClient()
    client.force_authenticate(user=user)
    url = reverse("organization-llms-list", kwargs={"organization_uuid": org.uuid})
    response = client.get(url)
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_custom_role_permissions_access(db):
    org = OrganizationFactory()
    user = UserFactory()
    _seed_llm_definitions()
    _ensure_llm_module(exposed_permissions=list(LLM_PERMISSION_KEYS))
    _create_active_subscription(org, Module.objects.get(key="LLM_MANAGEMENT"))
    role = Role.objects.create(
        organization=org,
        name="LLM Custom Role",
        description="",
        permissions=["llms:read"],
        role_type=Role.RoleType.USER_CUSTOM,
        created_by=user,
    )
    RoleAssignment.objects.create(user=user, role=role, organization=org, assigned_by=user)
    client = APIClient()
    client.force_authenticate(user=user)
    url = reverse("organization-llms-list", kwargs={"organization_uuid": org.uuid})
    response = client.get(url)
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_agent_manager_without_permissions_can_access(db):
    org = OrganizationFactory()
    user = UserFactory()
    _seed_llm_definitions()
    _ensure_llm_module(exposed_permissions=list(LLM_PERMISSION_KEYS))
    _create_active_subscription(org, Module.objects.get(key="LLM_MANAGEMENT"))
    role = Role.objects.create(
        organization=org,
        name=ROLE_AGENT_MANAGER,
        description="Editable agent manager role",
        permissions=[],
        role_type=Role.RoleType.USER_CUSTOM,
        created_by=user,
    )
    RoleAssignment.objects.create(user=user, role=role, organization=org, assigned_by=user)
    client = APIClient()
    client.force_authenticate(user=user)
    url = reverse("organization-llms-list", kwargs={"organization_uuid": org.uuid})
    response = client.get(url)
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_agent_manager_permission_removed_revokes_access(db):
    org = OrganizationFactory()
    user = UserFactory()
    # ensure user is not owner/admin exception
    other = UserFactory()
    org.created_by = other
    org.save(update_fields=["created_by", "updated_at"])
    org.account.created_by = other
    org.account.save(update_fields=["created_by", "updated_at"])
    _seed_llm_definitions()
    _ensure_llm_module(exposed_permissions=list(LLM_PERMISSION_KEYS))
    _create_active_subscription(org, Module.objects.get(key="LLM_MANAGEMENT"))

    role = Role.objects.create(
        organization=org,
        name=ROLE_AGENT_MANAGER,
        description="Editable agent manager role with llms:read",
        permissions=["llms:read"],
        role_type=Role.RoleType.USER_CUSTOM,
        created_by=user,
    )
    RoleAssignment.objects.create(user=user, role=role, organization=org, assigned_by=user)

    client = APIClient()
    client.force_authenticate(user=user)
    url = reverse("organization-llms-list", kwargs={"organization_uuid": org.uuid})
    # initial access allowed
    response = client.get(url)
    assert response.status_code == status.HTTP_200_OK

    # remove llms:read from role -> should revoke access immediately
    role.permissions = []
    role.save(update_fields=["permissions", "updated_at"])

    response = client.get(url)
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_account_owner_cannot_access_list_enable_disable(db):
    org = OrganizationFactory()
    user = UserFactory()
    org.account.created_by = user
    org.account.save(update_fields=["created_by", "updated_at"])
    _seed_llm_definitions()
    _ensure_llm_module(exposed_permissions=list(LLM_PERMISSION_KEYS))
    _create_active_subscription(org, Module.objects.get(key="LLM_MANAGEMENT"))
    client = APIClient()
    client.force_authenticate(user=user)
    list_url = reverse("organization-llms-available", kwargs={"organization_uuid": org.uuid})
    enable_url = reverse(
        "organization-llms-enable",
        kwargs={"organization_uuid": org.uuid, "model_key": "gpt-4o-mini"},
    )
    disable_url = reverse(
        "organization-llms-disable",
        kwargs={"organization_uuid": org.uuid, "model_key": "gpt-4o-mini"},
    )
    assert client.get(list_url).status_code == status.HTTP_403_FORBIDDEN
    assert client.post(enable_url).status_code == status.HTTP_403_FORBIDDEN
    assert client.post(disable_url).status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_disable_already_disabled_returns_400(llm_client):
    organization, user, client = llm_client
    enable_url = reverse(
        "organization-llms-enable",
        kwargs={"organization_uuid": organization.uuid, "model_key": "gpt-4o-mini"},
    )
    disable_url = reverse(
        "organization-llms-disable",
        kwargs={"organization_uuid": organization.uuid, "model_key": "gpt-4o-mini"},
    )
    assert client.post(enable_url).status_code == status.HTTP_200_OK
    assert client.post(disable_url).status_code == status.HTTP_200_OK
    response = client.post(disable_url)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
