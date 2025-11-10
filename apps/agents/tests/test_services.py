from django.test import TestCase

from apps.agents.definitions import LLM_DEFINITIONS
from apps.agents.models import Agent, OrganizationEnabledLLM
from apps.agents.services import clone_agent, save_agent_version
from apps.organizations.tests.factories import OrganizationFactory
from apps.users.tests.factories import UserFactory


class AgentServiceTests(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.organization = OrganizationFactory()
        self.llm_key = "gpt-4o-mini"
        OrganizationEnabledLLM.objects.create(
            organization=self.organization,
            model_key=self.llm_key,
            model_provider=LLM_DEFINITIONS[self.llm_key].provider,
            enabled_by=self.user,
        )
        self.agent = Agent.objects.create(
            organization=self.organization,
            name="Support Bot",
            description="Test agent",
            system_prompts="Always help customers politely.",
            llm_configuration={
                "modelKey": self.llm_key,
                "modelProvider": "OpenAI",
                "configuration": {"temperature": 0.3, "maxTokens": 256, "topP": 0.9},
            },
            tools_configuration=[],
            created_by=self.user,
            updated_by=self.user,
        )

    def test_save_agent_version_creates_snapshot(self):
        version = save_agent_version(self.agent, actor=self.user)
        self.assertEqual(version.version_number, 1)
        self.assertEqual(self.agent.current_version, version)

    def test_clone_agent_copies_configuration(self):
        save_agent_version(self.agent, actor=self.user)
        cloned = clone_agent(self.agent, created_by=self.user)
        self.assertEqual(cloned.system_prompts, self.agent.system_prompts)
        self.assertNotEqual(cloned.uuid, self.agent.uuid)
        self.assertEqual(cloned.current_version.version_number, 1)
