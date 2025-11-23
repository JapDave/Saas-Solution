import uuid

import pytest

from apps.agents.definitions import get_llm_definition
from apps.agents.models import Agent, OrganizationEnabledLLM, OrganizationEnabledTool
from apps.agents.serializers import AgentWriteSerializer
from apps.organizations.tests.factories import OrganizationFactory
from apps.users.tests.factories import UserFactory


@pytest.fixture
def agent_serializer_context(db):
    user = UserFactory()
    organization = OrganizationFactory()
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
    return {"user": user, "organization": organization, "llm_key": llm_key, "tool_key": tool_key}


@pytest.mark.django_db
def test_agent_serializer_creates_agent(agent_serializer_context):
    ctx = agent_serializer_context
    serializer = AgentWriteSerializer(
        data={
            "organization": str(ctx["organization"].uuid),
            "name": "Support Bot",
            "description": "Handles support inquiries",
            "system_prompts": "You are a helpful assistant.",
            "llm_configuration": {
                "modelKey": ctx["llm_key"],
                "modelProvider": "OpenAI",
                "configuration": {
                    "temperature": 0.2,
                    "maxTokens": 512,
                    "topP": 0.9,
                },
            },
            "tools_configuration": [
                {
                    "toolKey": ctx["tool_key"],
                    "configuration": {
                        "collection_id": str(uuid.uuid4()),
                    },
                }
            ],
        },
        context={"request": type("obj", (), {"user": ctx["user"]})},
    )
    assert serializer.is_valid(), serializer.errors
    agent = serializer.save()
    assert isinstance(agent, Agent)
    assert agent.llm_configuration["modelKey"] == ctx["llm_key"]
    assert agent.tools_configuration[0]["toolKey"] == ctx["tool_key"]
    assert agent.current_version is not None
    assert agent.versions.count() == 1
