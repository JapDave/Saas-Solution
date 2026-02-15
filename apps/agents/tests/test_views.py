import uuid

import pytest
from datetime import timedelta
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.agents.models import Agent, OrganizationEnabledLLM, OrganizationEnabledTool
from apps.llms.models import LLMDefinition
from apps.organizations.tests.factories import OrganizationFactory
from apps.products.models import Module
from apps.subscriptions.models import Subscription
from apps.users.models import UserOrganization
from apps.users.tests.factories import UserFactory
from apps.agents.definitions import _load_llm_definitions


AGENT_PERMISSIONS = [
    "agents:create",
    "agents:read",
    "agents:update",
    "agents:delete",
    "agents:versions:save",
    "agents:versions:switch",
    "agents:clone",
]


def _ensure_agents_subscription(org):
    module, _ = Module.objects.get_or_create(
        key="AGENTS_MANAGEMENT",
        defaults={
            "code": "AM",
            "name": "Agents Management",
            "description": "Agent management module",
            "exposed_permissions": AGENT_PERMISSIONS,
        },
    )
    if module.exposed_permissions != AGENT_PERMISSIONS:
        module.exposed_permissions = AGENT_PERMISSIONS
        module.save(update_fields=["exposed_permissions", "updated_at"])
    Subscription.objects.get_or_create(
        organization=org,
        module=module,
        defaults={
            "status": Subscription.Status.ACTIVE,
            "configuration": {},
            "start_date": timezone.now() - timedelta(days=1),
            "end_date": None,
        },
    )


@pytest.fixture
def agent_context(db):
    user = UserFactory()
    organization = OrganizationFactory()
    _ensure_agents_subscription(organization)
    UserOrganization.objects.create(
        user=user,
        organization=organization,
        permission_keys=AGENT_PERMISSIONS,
        assigned_by=user,
    )
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
                "maxTokens": {"type": "number", "required": False, "validation": {"min": 1, "max": 128000}},
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
    client = APIClient()
    client.force_authenticate(user=user)
    return {
        "client": client,
        "organization": organization,
        "user": user,
        "llm_key": llm_def.model_key,
    }


def _version_payload(ctx, *, name="Support Bot", system_prompts="Be helpful.", temperature=0.2):
    return {
        "name": name,
        "description": "Helps customers",
        "systemPrompts": system_prompts,
        "llmConfiguration": {
            "modelKey": ctx["llm_key"],
            "modelProvider": "OpenAI",
            "configuration": {"temperature": temperature, "maxTokens": 256},
        },
        "toolsConfiguration": [
            {"toolKey": "calculator", "configuration": {"expression": "2+2"}}
        ],
    }


@pytest.mark.django_db
def test_create_agent_draft_no_version(agent_context):
    client = agent_context["client"]
    org_id = agent_context["organization"].uuid
    response = client.post(
        f"/api/agents/organizations/{org_id}/",
        {"name": "Support Bot", "description": "Helps customers"},
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.data
    assert data["state"] == Agent.AgentState.DRAFT
    assert data["currentVersionId"] is None
    assert Agent.objects.count() == 1
    agent = Agent.objects.first()
    assert agent.versions.count() == 0


@pytest.mark.django_db
def test_save_version_creates_and_idempotent(agent_context):
    client = agent_context["client"]
    org_id = agent_context["organization"].uuid
    create = client.post(
        f"/api/agents/organizations/{org_id}/",
        {"name": "Support Bot", "description": "Helps customers"},
        format="json",
    )
    agent_id = create.data["id"]

    payload = _version_payload(agent_context)
    version_resp = client.post(
        f"/api/agents/organizations/{org_id}/{agent_id}/versions/",
        payload,
        format="json",
    )
    assert version_resp.status_code == status.HTTP_201_CREATED
    assert version_resp.data["versionNumber"] == 1

    idempotent = client.post(
        f"/api/agents/organizations/{org_id}/{agent_id}/versions/",
        payload,
        format="json",
    )
    assert idempotent.status_code == status.HTTP_200_OK
    assert idempotent.data["versionNumber"] == 1
    agent = Agent.objects.get(uuid=agent_id)
    assert agent.versions.count() == 1


@pytest.mark.django_db
def test_switch_version(agent_context):
    client = agent_context["client"]
    org_id = agent_context["organization"].uuid
    create = client.post(
        f"/api/agents/organizations/{org_id}/",
        {"name": "Support Bot", "description": "Helps customers"},
        format="json",
    )
    agent_id = create.data["id"]
    v1 = client.post(
        f"/api/agents/organizations/{org_id}/{agent_id}/versions/",
        _version_payload(agent_context, system_prompts="Version 1"),
        format="json",
    ).data
    v2 = client.post(
        f"/api/agents/organizations/{org_id}/{agent_id}/versions/",
        _version_payload(agent_context, system_prompts="Version 2"),
        format="json",
    ).data

    switch_resp = client.post(
        f"/api/agents/organizations/{org_id}/{agent_id}/versions/{v1['id']}/switch/",
        {},
        format="json",
    )
    assert switch_resp.status_code == status.HTTP_200_OK
    assert switch_resp.data["currentVersionId"] == v1["id"]


@pytest.mark.django_db
def test_patch_ignores_system_prompts(agent_context):
    client = agent_context["client"]
    org_id = agent_context["organization"].uuid
    create = client.post(
        f"/api/agents/organizations/{org_id}/",
        {"name": "Support Bot", "description": "Helps customers"},
        format="json",
    )
    agent_id = create.data["id"]
    v1 = client.post(
        f"/api/agents/organizations/{org_id}/{agent_id}/versions/",
        _version_payload(agent_context),
        format="json",
    ).data

    patch_resp = client.patch(
        f"/api/agents/organizations/{org_id}/{agent_id}/",
        {"systemPrompts": "Injected"},
        format="json",
    )
    assert patch_resp.status_code == status.HTTP_200_OK
    agent = Agent.objects.get(uuid=agent_id)
    assert agent.current_version.uuid == uuid.UUID(v1["id"])


@pytest.mark.django_db
def test_subscription_required(agent_context):
    client = agent_context["client"]
    org = OrganizationFactory()
    resp = client.get(f"/api/agents/organizations/{org.uuid}/")
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert resp.data.get("code") == "SUBSCRIPTION_REQUIRED"


@pytest.mark.django_db
def test_invalid_llm_configuration_rejected(agent_context):
    client = agent_context["client"]
    org_id = agent_context["organization"].uuid
    create = client.post(
        f"/api/agents/organizations/{org_id}/",
        {"name": "Support Bot", "description": "Helps customers"},
        format="json",
    )
    agent_id = create.data["id"]
    payload = _version_payload(agent_context, temperature=1.5)
    resp = client.post(
        f"/api/agents/organizations/{org_id}/{agent_id}/versions/",
        payload,
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data.get("code") in {"INVALID_LLM_CONFIGURATION", "LLM_NOT_ENABLED"}


@pytest.mark.django_db
def test_duplicate_tool_rejected(agent_context):
    client = agent_context["client"]
    org_id = agent_context["organization"].uuid
    create = client.post(
        f"/api/agents/organizations/{org_id}/",
        {"name": "Support Bot", "description": "Helps customers"},
        format="json",
    )
    agent_id = create.data["id"]
    payload = _version_payload(agent_context)
    payload["toolsConfiguration"].append({"toolKey": "calculator", "configuration": {"expression": "3+3"}})
    resp = client.post(
        f"/api/agents/organizations/{org_id}/{agent_id}/versions/",
        payload,
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data.get("code") == "DUPLICATE_TOOL"


@pytest.mark.django_db
def test_duplicate_agent_name_conflict(agent_context):
    client = agent_context["client"]
    org_id = agent_context["organization"].uuid
    first = client.post(
        f"/api/agents/organizations/{org_id}/",
        {"name": "Support Bot", "description": "Helps customers"},
        format="json",
    )
    assert first.status_code == status.HTTP_201_CREATED

    resp = client.post(
        f"/api/agents/organizations/{org_id}/",
        {"name": "Support Bot", "description": "Duplicate"},
        format="json",
    )
    assert resp.status_code == status.HTTP_409_CONFLICT
    assert resp.data.get("code") == "AGENT_NAME_NOT_UNIQUE"


@pytest.mark.django_db
def test_archive_read_only_blocks_updates_and_saves(agent_context):
    client = agent_context["client"]
    org_id = agent_context["organization"].uuid
    create = client.post(
        f"/api/agents/organizations/{org_id}/",
        {"name": "Support Bot", "description": "Helps customers"},
        format="json",
    )
    agent_id = create.data["id"]
    client.post(
        f"/api/agents/organizations/{org_id}/{agent_id}/versions/",
        _version_payload(agent_context),
        format="json",
    )
    activate = client.post(f"/api/agents/organizations/{org_id}/{agent_id}/activate/", {}, format="json")
    assert activate.status_code == status.HTTP_200_OK
    archive = client.post(f"/api/agents/organizations/{org_id}/{agent_id}/archive/", {}, format="json")
    assert archive.status_code == status.HTTP_200_OK

    patch_resp = client.patch(
        f"/api/agents/organizations/{org_id}/{agent_id}/",
        {"name": "Updated Name"},
        format="json",
    )
    assert patch_resp.status_code == status.HTTP_400_BAD_REQUEST
    assert patch_resp.data.get("code") == "INVALID_STATE_TRANSITION"

    version_resp = client.post(
        f"/api/agents/organizations/{org_id}/{agent_id}/versions/",
        _version_payload(agent_context, system_prompts="New prompts"),
        format="json",
    )
    assert version_resp.status_code == status.HTTP_400_BAD_REQUEST
    assert version_resp.data.get("code") == "INVALID_STATE_TRANSITION"


@pytest.mark.django_db
def test_version_numbers_increment(agent_context):
    client = agent_context["client"]
    org_id = agent_context["organization"].uuid
    create = client.post(
        f"/api/agents/organizations/{org_id}/",
        {"name": "Support Bot", "description": "Helps customers"},
        format="json",
    )
    agent_id = create.data["id"]
    v1 = client.post(
        f"/api/agents/organizations/{org_id}/{agent_id}/versions/",
        _version_payload(agent_context, system_prompts="V1"),
        format="json",
    )
    v2 = client.post(
        f"/api/agents/organizations/{org_id}/{agent_id}/versions/",
        _version_payload(agent_context, system_prompts="V2"),
        format="json",
    )
    assert v1.data["versionNumber"] == 1
    assert v2.data["versionNumber"] == 2


@pytest.mark.django_db
def test_patch_updates_metadata(agent_context):
    client = agent_context["client"]
    org_id = agent_context["organization"].uuid
    user = agent_context["user"]
    create = client.post(
        f"/api/agents/organizations/{org_id}/",
        {"name": "Support Bot", "description": "Helps customers"},
        format="json",
    )
    agent_id = create.data["id"]
    agent = Agent.objects.get(uuid=agent_id)
    original_updated_at = agent.updated_at

    resp = client.patch(
        f"/api/agents/organizations/{org_id}/{agent_id}/",
        {"description": "Updated"},
        format="json",
    )
    assert resp.status_code == status.HTTP_200_OK
    agent.refresh_from_db()
    assert agent.updated_by_id == user.id
    assert agent.updated_at >= original_updated_at
    assert agent.versions.count() == 0


@pytest.mark.django_db
def test_llm_disabled_blocks_save(agent_context):
    client = agent_context["client"]
    org = agent_context["organization"]
    org_id = org.uuid
    create = client.post(
        f"/api/agents/organizations/{org_id}/",
        {"name": "Support Bot", "description": "Helps customers"},
        format="json",
    )
    agent_id = create.data["id"]
    OrganizationEnabledLLM.objects.filter(organization=org, model_key=agent_context["llm_key"]).update(
        disabled_at=timezone.now()
    )
    resp = client.post(
        f"/api/agents/organizations/{org_id}/{agent_id}/versions/",
        _version_payload(agent_context),
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data.get("code") == "LLM_NOT_ENABLED"


@pytest.mark.django_db
def test_clone_naming_increments(agent_context):
    client = agent_context["client"]
    org_id = agent_context["organization"].uuid
    create = client.post(
        f"/api/agents/organizations/{org_id}/",
        {"name": "Sales Bot", "description": "Handles sales"},
        format="json",
    )
    agent_id = create.data["id"]
    client.post(
        f"/api/agents/organizations/{org_id}/{agent_id}/versions/",
        _version_payload(agent_context, name="Sales Bot"),
        format="json",
    )

    clone1 = client.post(
        f"/api/agents/organizations/{org_id}/{agent_id}/clone/",
        {},
        format="json",
    )
    assert clone1.status_code == status.HTTP_201_CREATED
    assert clone1.data["name"] == "Copy of Sales Bot"

    clone2 = client.post(
        f"/api/agents/organizations/{org_id}/{agent_id}/clone/",
        {},
        format="json",
    )
    assert clone2.status_code == status.HTTP_201_CREATED
    assert clone2.data["name"] == "Copy of Sales Bot (2)"


@pytest.mark.django_db
def test_subscription_limit_exceeded(agent_context):
    client = agent_context["client"]
    org = agent_context["organization"]
    subscription = Subscription.objects.get(organization=org, module__key="AGENTS_MANAGEMENT")
    subscription.configuration = {"agents_max_agents_per_org": 1}
    subscription.save(update_fields=["configuration", "updated_at"])

    first = client.post(
        f"/api/agents/organizations/{org.uuid}/",
        {"name": "Support Bot", "description": "Helps customers"},
        format="json",
    )
    assert first.status_code == status.HTTP_201_CREATED

    second = client.post(
        f"/api/agents/organizations/{org.uuid}/",
        {"name": "Support Bot 2", "description": "Second"},
        format="json",
    )
    assert second.status_code == status.HTTP_409_CONFLICT
    assert second.data.get("code") == "SUBSCRIPTION_LIMIT_EXCEEDED"
