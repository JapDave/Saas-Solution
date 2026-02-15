import pytest

from apps.agents.models import Agent, OrganizationEnabledLLM, OrganizationEnabledTool
from apps.agents.services import save_agent_version
from apps.llms.models import LLMDefinition
from apps.organizations.tests.factories import OrganizationFactory
from apps.users.tests.factories import UserFactory
from apps.agents.definitions import _load_llm_definitions


@pytest.fixture
def agent_service_context(db):
    user = UserFactory()
    organization = OrganizationFactory()
    llm_def, _ = LLMDefinition.objects.get_or_create(
        model_key="gpt-4o-mini",
        defaults={
            "model_provider": "OpenAI",
            "display_name": "GPT-4o Mini",
            "description": "Test model",
            "supported_modalities": ["text"],
            "max_context_tokens": 128000,
            "model_configuration": {
                "temperature": {"type": "number", "required": False, "validation": {"min": 0, "max": 1}},
            },
        },
    )
    _load_llm_definitions.cache_clear()
    OrganizationEnabledLLM.objects.get_or_create(
        organization=organization,
        model_key=llm_def.model_key,
        defaults={
            "model_provider": llm_def.model_provider,
            "display_name": llm_def.display_name,
            "enabled_by": user,
        },
    )
    OrganizationEnabledTool.objects.get_or_create(
        organization=organization,
        tool_key="calculator",
        defaults={"enabled_by": user},
    )
    agent = Agent.objects.create(
        organization=organization,
        name="Support Bot",
        description="Test agent",
        created_by=user,
        updated_by=user,
    )
    return {"user": user, "organization": organization, "agent": agent}


@pytest.mark.django_db
def test_save_agent_version_creates_snapshot(agent_service_context):
    agent = agent_service_context["agent"]
    user = agent_service_context["user"]
    version, created = save_agent_version(
        agent,
        actor=user,
        name=agent.name,
        description=agent.description,
        system_prompts="Always help customers politely.",
        llm_configuration={
            "modelKey": "gpt-4o-mini",
            "modelProvider": "OpenAI",
            "configuration": {"temperature": 0.3},
        },
        tools_configuration=[{"toolKey": "calculator", "configuration": {"expression": "1+1"}}],
    )
    assert created is True
    assert version.version_number == 1
    agent.refresh_from_db()
    assert agent.current_version == version
