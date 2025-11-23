import pytest

from apps.agents.definitions import get_llm_definition
from apps.agents.models import Agent, OrganizationEnabledLLM
from apps.agents.services import clone_agent, save_agent_version
from apps.organizations.tests.factories import OrganizationFactory
from apps.users.tests.factories import UserFactory


@pytest.fixture
def agent_service_context(db):
    user = UserFactory()
    organization = OrganizationFactory()
    llm_key = "gpt-4o-mini"
    llm_def = get_llm_definition(llm_key)
    OrganizationEnabledLLM.objects.create(
        organization=organization,
        model_key=llm_key,
        model_provider=llm_def.provider if llm_def else "OpenAI",
        enabled_by=user,
    )
    agent = Agent.objects.create(
        organization=organization,
        name="Support Bot",
        description="Test agent",
        system_prompts="Always help customers politely.",
        llm_configuration={
            "modelKey": llm_key,
            "modelProvider": "OpenAI",
            "configuration": {"temperature": 0.3, "maxTokens": 256, "topP": 0.9},
        },
        tools_configuration=[],
        created_by=user,
        updated_by=user,
    )
    return {"user": user, "organization": organization, "agent": agent}


@pytest.mark.django_db
def test_save_agent_version_creates_snapshot(agent_service_context):
    agent = agent_service_context["agent"]
    user = agent_service_context["user"]
    version = save_agent_version(agent, actor=user)
    assert version.version_number == 1
    agent.refresh_from_db()
    assert agent.current_version == version


@pytest.mark.django_db
def test_clone_agent_copies_configuration(agent_service_context):
    agent = agent_service_context["agent"]
    user = agent_service_context["user"]
    save_agent_version(agent, actor=user)
    cloned = clone_agent(agent, created_by=user)
    assert cloned.system_prompts == agent.system_prompts
    assert cloned.uuid != agent.uuid
    assert cloned.current_version.version_number == 1
