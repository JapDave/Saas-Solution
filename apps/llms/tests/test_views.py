import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.agents.models import OrganizationEnabledLLM
from apps.llms.models import LLMDefinition
from apps.organizations.tests.factories import OrganizationFactory
from apps.products.models import Module
from apps.roles.constants import LLM_PERMISSION_KEYS, ROLE_SAAS_ADMINISTRATOR
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
    assert response.json()["code"] == "SUBSCRIPTION_LIMIT_EXCEEDED"


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
