import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.agents.models import OrganizationEnabledTool
from apps.knowledge_base.models import Collection
from apps.organizations.tests.factories import OrganizationFactory
from apps.products.models import Module
from apps.roles.constants import TOOL_PERMISSION_KEYS
from apps.subscriptions.models import Subscription
from apps.users.models import UserOrganization
from apps.users.tests.factories import UserFactory


@pytest.fixture
def tool_client(db):
    organization = OrganizationFactory()
    user = UserFactory()
    UserOrganization.objects.create(
        user=user,
        organization=organization,
        permission_keys=list(TOOL_PERMISSION_KEYS),
        assigned_by=user,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    module, _ = Module.objects.get_or_create(
        key="TOOLS_MANAGEMENT",
        defaults={
            "code": "TOOL",
            "name": "Tools Management",
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
            "configuration": {"tools_max_enabled_per_org": 1},
        },
    )
    return organization, user, client


@pytest.mark.django_db
def test_list_tools(tool_client):
    _, _, client = tool_client
    response = client.get(reverse("tool-list"))
    assert response.status_code == status.HTTP_200_OK
    assert response.json()


@pytest.mark.django_db
def test_enable_tool(tool_client):
    organization, _, client = tool_client
    enable_url = reverse(
        "organization-tools-enable",
        kwargs={"organization_uuid": organization.uuid, "tool_key": "calculator"},
    )
    response = client.post(enable_url)
    assert response.status_code == status.HTTP_200_OK
    assert OrganizationEnabledTool.objects.filter(organization=organization, tool_key="calculator").exists()


@pytest.mark.django_db
def test_tool_limit(tool_client):
    organization, _, client = tool_client
    first = reverse(
        "organization-tools-enable",
        kwargs={"organization_uuid": organization.uuid, "tool_key": "calculator"},
    )
    assert client.post(first).status_code == status.HTTP_200_OK
    second = reverse(
        "organization-tools-enable",
        kwargs={"organization_uuid": organization.uuid, "tool_key": "ocr_extractor"},
    )
    response = client.post(second)
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["code"] == "SUBSCRIPTION_LIMIT_EXCEEDED"


@pytest.mark.django_db
def test_validate_kb_tool(tool_client):
    organization, _, client = tool_client
    collection = Collection.objects.create(
        organization=organization,
        name="Support KB",
        created_by=None,
        updated_by=None,
    )
    enable_url = reverse(
        "organization-tools-enable",
        kwargs={"organization_uuid": organization.uuid, "tool_key": "kb_retriever"},
    )
    client.post(enable_url)
    payload = {
        "organization_uuid": str(organization.uuid),
        "toolKey": "kb_retriever",
        "configuration": {"collection_id": str(collection.uuid), "maxResults": 5},
    }
    response = client.post(reverse("tool-validate"), payload, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["toolKey"] == "kb_retriever"
