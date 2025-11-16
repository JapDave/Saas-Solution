import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.integrations.models import Integration
from apps.organizations.tests.factories import OrganizationFactory
from apps.products.models import Module
from apps.roles.constants import INTEGRATION_PERMISSION_KEYS
from apps.subscriptions.models import Subscription
from apps.users.models import UserOrganization
from apps.users.tests.factories import UserFactory


@pytest.fixture
def integration_manager(db):
    organization = OrganizationFactory()
    user = UserFactory()
    UserOrganization.objects.create(
        user=user,
        organization=organization,
        permission_keys=list(INTEGRATION_PERMISSION_KEYS),
        assigned_by=user,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    module, _ = Module.objects.get_or_create(
        key="INTEGRATIONS_MANAGEMENT",
        defaults={
            "code": "INTG",
            "name": "Integrations Management",
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
            "configuration": {
                "integrations.api": {"enabled": True, "maxInstances": 5, "maxInvocationsPerMonth": 5000},
                "integrations.webhook": {"enabled": True, "maxInstances": 5, "maxInvocationsPerMonth": 5000},
            },
        },
    )
    return organization, user, client


def api_payload():
    return {
        "integration_type": "api",
        "name": "CRM Lookup",
        "description": "Lookup customer info",
        "url": "https://api.example.com/customers/{customerId}",
        "method": "GET",
        "headers": [{"key": "Authorization", "value": "Bearer token"}],
        "parameters": [
            {"key": "customerId", "name": "Customer ID", "type": "path", "required": True, "description": ""},
        ],
        "response_mappings": [{"key": "customerName", "name": "Customer Name", "jsonPath": "$.data.name"}],
    }


def webhook_payload():
    return {
        "integration_type": "webhook",
        "name": "Order Notifications",
        "response_mappings": [{"key": "orderTotal", "name": "Order Total", "jsonPath": "$.order.total"}],
        "webhook_sample_payload": {"order": {"total": 99}},
    }


@pytest.mark.django_db
def test_create_api_integration(integration_manager):
    organization, _, client = integration_manager
    url = reverse("organization-integrations-list", kwargs={"organization_uuid": organization.uuid})
    response = client.post(url, api_payload(), format="json")
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["integration_type"] == "api"
    assert data["url"].endswith("{customerId}")


@pytest.mark.django_db
def test_create_webhook_integration_returns_secret_once(integration_manager):
    organization, _, client = integration_manager
    url = reverse("organization-integrations-list", kwargs={"organization_uuid": organization.uuid})
    response = client.post(url, webhook_payload(), format="json")
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["integration_type"] == "webhook"
    assert data["webhook_secret"].startswith("whsec_")
    detail_url = reverse(
        "organization-integrations-detail",
        kwargs={"organization_uuid": organization.uuid, "uuid": data["uuid"]},
    )
    follow_up = client.get(detail_url)
    assert follow_up.status_code == status.HTTP_200_OK
    assert follow_up.json()["webhook_secret"] is None


@pytest.mark.django_db
def test_activate_deactivate_and_regenerate_secret(integration_manager):
    organization, _, client = integration_manager
    url = reverse("organization-integrations-list", kwargs={"organization_uuid": organization.uuid})
    webhook = client.post(url, webhook_payload(), format="json").json()
    detail_kwargs = {"organization_uuid": organization.uuid, "uuid": webhook["uuid"]}

    deactivate = client.post(
        reverse("organization-integrations-deactivate", kwargs=detail_kwargs),
    )
    assert deactivate.status_code == status.HTTP_200_OK
    assert deactivate.json()["state"] == Integration.IntegrationState.INACTIVE

    activate = client.post(reverse("organization-integrations-activate", kwargs=detail_kwargs))
    assert activate.status_code == status.HTTP_200_OK
    assert activate.json()["state"] == Integration.IntegrationState.ACTIVE

    regen = client.post(
        reverse("organization-integrations-regenerate-secret", kwargs=detail_kwargs),
    )
    assert regen.status_code == status.HTTP_200_OK
    assert regen.json()["webhook_secret"].startswith("whsec_")


@pytest.mark.django_db
def test_mock_test_action_returns_payload(integration_manager):
    organization, _, client = integration_manager
    url = reverse("organization-integrations-list", kwargs={"organization_uuid": organization.uuid})
    integration = client.post(url, api_payload(), format="json").json()
    test_url = reverse(
        "organization-integrations-test",
        kwargs={"organization_uuid": organization.uuid, "uuid": integration["uuid"]},
    )
    response = client.post(test_url, {"parameters": {"customerId": "CUST-1"}}, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["success"] is True


@pytest.mark.django_db
def test_analytics_endpoint(integration_manager):
    organization, _, client = integration_manager
    url = reverse("organization-integrations-list", kwargs={"organization_uuid": organization.uuid})
    client.post(url, api_payload(), format="json")
    analytics_url = reverse("integration-analytics", kwargs={"organization_uuid": organization.uuid})
    response = client.get(analytics_url)
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert any(item["integration_type"] == "api" for item in body)
