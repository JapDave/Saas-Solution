import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.flows.models import Flow, FlowVersion
from apps.organizations.tests.factories import OrganizationFactory
from apps.roles.constants import FLOW_PERMISSION_KEYS
from apps.users.models import UserOrganization
from apps.users.tests.factories import UserFactory


@pytest.fixture
def flow_manager(db):
    organization = OrganizationFactory()
    user = UserFactory()
    UserOrganization.objects.create(
        user=user,
        organization=organization,
        permission_keys=list(FLOW_PERMISSION_KEYS),
        assigned_by=user,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return user, organization, client


def _flow_payload():
    return {
        "name": "Demo Flow",
        "description": "Demo workflow",
        "flow_configurations": {"autoRetry": True},
        "flow_json": {
            "nodes": [
                {
                    "id": "trigger-1",
                    "type": "trigger",
                    "position": {"x": 0, "y": 0},
                    "data": {"triggerType": "webhook", "eventType": "signup"},
                }
            ],
            "edges": [],
            "viewport": {"x": 0, "y": 0, "zoom": 1.0},
        },
    }


@pytest.mark.django_db
def test_create_flow_initializes_draft_version(flow_manager):
    _, organization, client = flow_manager
    url = reverse("organization-flows-list", kwargs={"organization_uuid": organization.uuid})

    response = client.post(url, _flow_payload(), format="json")
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["name"] == "Demo Flow"
    assert body["active_versions"]["draft"]["version_number"] == 1
    flow = Flow.objects.get(uuid=body["uuid"])
    assert flow.versions.count() == 1


@pytest.mark.django_db
def test_publish_and_disable_flow(flow_manager):
    _, organization, client = flow_manager
    create_url = reverse("organization-flows-list", kwargs={"organization_uuid": organization.uuid})
    flow_id = client.post(create_url, _flow_payload(), format="json").json()["uuid"]

    publish_url = reverse(
        "organization-flows-publish",
        kwargs={"organization_uuid": organization.uuid, "uuid": flow_id},
    )
    publish_response = client.post(publish_url)
    assert publish_response.status_code == status.HTTP_200_OK
    assert publish_response.json()["state"] == FlowVersion.FlowVersionState.PUBLISHED

    disable_url = reverse(
        "organization-flows-disable",
        kwargs={"organization_uuid": organization.uuid, "uuid": flow_id},
    )
    disable_response = client.post(disable_url)
    assert disable_response.status_code == status.HTTP_200_OK
    assert disable_response.json()["state"] == FlowVersion.FlowVersionState.DISABLED

    enable_url = reverse(
        "organization-flows-enable",
        kwargs={"organization_uuid": organization.uuid, "uuid": flow_id},
    )
    enable_response = client.post(enable_url)
    assert enable_response.status_code == status.HTTP_200_OK
    assert enable_response.json()["state"] == FlowVersion.FlowVersionState.PUBLISHED


@pytest.mark.django_db
def test_version_conflict_returns_409(flow_manager):
    _, organization, client = flow_manager
    list_url = reverse("organization-flows-list", kwargs={"organization_uuid": organization.uuid})
    detail = client.post(list_url, _flow_payload(), format="json").json()
    flow_uuid = detail["uuid"]

    versions_url = reverse(
        "flow-versions-list",
        kwargs={"organization_uuid": organization.uuid, "flow_uuid": flow_uuid},
    )
    initial_version = client.get(versions_url).json()["results"][0]
    payload = _flow_payload()
    payload["previous_version_uuid"] = initial_version["uuid"]

    ok_response = client.post(versions_url, payload, format="json")
    assert ok_response.status_code == status.HTTP_201_CREATED

    conflict_response = client.post(versions_url, payload, format="json")
    assert conflict_response.status_code == status.HTTP_409_CONFLICT
    assert conflict_response.json()["code"] == "VERSION_CONFLICT"


@pytest.mark.django_db
def test_clone_flow_creates_independent_flow(flow_manager):
    _, organization, client = flow_manager
    list_url = reverse("organization-flows-list", kwargs={"organization_uuid": organization.uuid})
    flow_uuid = client.post(list_url, _flow_payload(), format="json").json()["uuid"]
    publish_url = reverse(
        "organization-flows-publish",
        kwargs={"organization_uuid": organization.uuid, "uuid": flow_uuid},
    )
    client.post(publish_url)

    clone_url = reverse(
        "organization-flows-clone",
        kwargs={"organization_uuid": organization.uuid, "uuid": flow_uuid},
    )
    clone_response = client.post(clone_url)
    assert clone_response.status_code == status.HTTP_201_CREATED
    clone_body = clone_response.json()
    assert clone_body["name"].startswith("Copy of")
    assert Flow.objects.filter(organization=organization).count() == 2
