from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.agents.definitions import LLM_DEFINITIONS
from apps.agents.models import Agent, OrganizationEnabledLLM, OrganizationEnabledTool
from apps.organizations.tests.factories import OrganizationFactory
from apps.users.models import UserOrganization
from apps.users.tests.factories import UserFactory


class AgentViewTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.organization = OrganizationFactory()
        UserOrganization.objects.create(
            user=self.user,
            organization=self.organization,
            permission_keys=["agents:admin"],
            assigned_by=self.user,
        )
        self.client.force_authenticate(user=self.user)
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

    def _agent_payload(self):
        return {
            "organization": str(self.organization.uuid),
            "name": "Support Bot",
            "description": "Helps customers",
            "system_prompts": "Be kind to every customer.",
            "llm_configuration": {
                "modelKey": self.llm_key,
                "modelProvider": "OpenAI",
                "configuration": {"temperature": 0.1, "maxTokens": 256, "topP": 0.9},
            },
            "tools_configuration": [
                {
                    "toolKey": self.tool_key,
                    "configuration": {"collection_id": "abc-123"},
                }
            ],
        }

    def test_create_agent_via_api(self):
        response = self.client.post("/api/agents/", self._agent_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Agent.objects.count(), 1)
        self.assertEqual(response.data["current_version_number"], 1)

    def test_save_version_endpoint(self):
        response = self.client.post("/api/agents/", self._agent_payload(), format="json")
        agent_uuid = response.data["uuid"]
        url = f"/api/agents/{agent_uuid}/versions/"
        version_response = self.client.post(url, {}, format="json")
        self.assertEqual(version_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(version_response.data["version_number"], 2)

    def test_available_llms_endpoint(self):
        url = f"/api/organizations/{self.organization.uuid}/llms/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(any(item["modelKey"] == self.llm_key for item in response.data))

    def test_available_tools_endpoint(self):
        url = f"/api/organizations/{self.organization.uuid}/tools/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(any(item["toolKey"] == self.tool_key for item in response.data))
