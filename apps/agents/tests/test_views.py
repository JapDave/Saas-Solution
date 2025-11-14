import uuid

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.agents.definitions import get_llm_definition
from apps.agents.models import Agent, OrganizationEnabledLLM, OrganizationEnabledTool
from apps.organizations.tests.factories import OrganizationFactory
from apps.users.models import UserOrganization
from apps.users.tests.factories import UserFactory


@pytest.fixture
def agent_context(db):
    user = UserFactory()
    organization = OrganizationFactory()
    UserOrganization.objects.create(
        user=user,
        organization=organization,
        permission_keys=["agents:admin"],
        assigned_by=user,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    llm_key = "gpt-4o-mini"
    tool_key = "kb_retriever"
    llm_def = get_llm_definition(llm_key)
    OrganizationEnabledLLM.objects.create(
        organization=organization,
        model_key=llm_key,
        model_provider=llm_def.provider if llm_def else "OpenAI",
        enabled_by=user,
    )
    OrganizationEnabledTool.objects.create(
        organization=organization,
        tool_key=tool_key,
        enabled_by=user,
    )
    return {
        "client": client,
        "organization": organization,
        "llm_key": llm_key,
        "tool_key": tool_key,
    }


def _agent_payload(context):
    return {
        "organization": str(context["organization"].uuid),
        "name": "Support Bot",
        "description": "Helps customers",
        "system_prompts": "Be kind to every customer.",
        "llm_configuration": {
            "modelKey": context["llm_key"],
            "modelProvider": "OpenAI",
            "configuration": {"temperature": 0.1, "maxTokens": 256, "topP": 0.9},
        },
        "tools_configuration": [
            {
                "toolKey": context["tool_key"],
                "configuration": {"collection_id": str(uuid.uuid4())},
            }
        ],
    }


@pytest.mark.django_db
def test_create_agent_via_api(agent_context):
    response = agent_context["client"].post("/api/agents/", _agent_payload(agent_context), format="json")
    assert response.status_code == status.HTTP_201_CREATED
    assert Agent.objects.count() == 1


@pytest.mark.django_db
def test_save_version_endpoint(agent_context):
    client = agent_context["client"]
    response = client.post("/api/agents/", _agent_payload(agent_context), format="json")
    assert response.status_code == status.HTTP_201_CREATED
    version_url = f"/api/agents/{response.data['uuid']}/versions/"
    version_response = client.post(version_url, {}, format="json")
    assert version_response.status_code == status.HTTP_201_CREATED
    assert version_response.data["version_number"] == 2


@pytest.mark.django_db
def test_available_llms_endpoint(agent_context):
    url = f"/api/organizations/{agent_context['organization'].uuid}/llms/"
    response = agent_context["client"].get(url)
    assert response.status_code == status.HTTP_200_OK
    assert any(item["modelKey"] == agent_context["llm_key"] for item in response.data)


@pytest.mark.django_db
def test_available_tools_endpoint(agent_context):
    url = f"/api/organizations/{agent_context['organization'].uuid}/tools/"
    response = agent_context["client"].get(url)
    assert response.status_code == status.HTTP_200_OK
    assert any(item["toolKey"] == agent_context["tool_key"] for item in response.data)
