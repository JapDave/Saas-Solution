from django.test import TestCase

from apps.agents.definitions import LLM_DEFINITIONS
from apps.agents.models import Agent, OrganizationEnabledLLM, OrganizationEnabledTool
from apps.agents.serializers import AgentWriteSerializer
from apps.organizations.tests.factories import OrganizationFactory
from apps.users.tests.factories import UserFactory


class AgentSerializerTests(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.organization = OrganizationFactory()
        self.llm_key = "gpt-4o-mini"
        self.tool_key = "kb_retriever"
        OrganizationEnabledLLM.objects.create(
            organization=self.organization,
            model_key=self.llm_key,
            model_provider=LLM_DEFINITIONS[self.llm_key].provider,
            enabled_by=self.user,
        )
        OrganizationEnabledTool.objects.create(
            organization=self.organization,
            tool_key=self.tool_key,
            enabled_by=self.user,
        )

    def test_agent_serializer_creates_agent(self):
        serializer = AgentWriteSerializer(
            data={
                "organization": str(self.organization.uuid),
                "name": "Support Bot",
                "description": "Handles support inquiries",
                "system_prompts": "You are a helpful assistant.",
                "llm_configuration": {
                    "modelKey": self.llm_key,
                    "modelProvider": "OpenAI",
                    "configuration": {
                        "temperature": 0.2,
                        "maxTokens": 512,
                        "topP": 0.9,
                    },
                },
                "tools_configuration": [
                    {
                        "toolKey": self.tool_key,
                        "configuration": {
                            "collection_id": "123",
                        },
                    }
                ],
            },
            context={"request": type("obj", (), {"user": self.user})},
        )
        assert serializer.is_valid(), serializer.errors
        agent = serializer.save()
        self.assertIsInstance(agent, Agent)
        self.assertEqual(agent.llm_configuration["modelKey"], self.llm_key)
        self.assertEqual(agent.tools_configuration[0]["toolKey"], self.tool_key)
        self.assertIsNotNone(agent.current_version)
        self.assertEqual(agent.versions.count(), 1)
