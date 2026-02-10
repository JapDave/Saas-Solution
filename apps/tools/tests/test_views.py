import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.agents.models import OrganizationEnabledTool
from apps.organizations.tests.factories import OrganizationFactory
from apps.products.models import Module
from apps.roles.constants import ROLE_SAAS_ADMINISTRATOR, TOOL_PERMISSION_KEYS
from apps.roles.models import Role, RoleAssignment
from apps.subscriptions.models import Subscription
from apps.users.models import UserOrganization
from apps.users.tests.factories import UserFactory


@pytest.fixture
def tool_context(db):
    organization = OrganizationFactory()
    org_user = UserFactory()
    UserOrganization.objects.create(
        user=org_user,
        organization=organization,
        permission_keys=list(TOOL_PERMISSION_KEYS),
        assigned_by=org_user,
    )
    org_client = APIClient()
    org_client.force_authenticate(user=org_user)

    saas_user = UserFactory()
    role, _ = Role.objects.get_or_create(
        name=ROLE_SAAS_ADMINISTRATOR,
        organization=None,
        defaults={
            "role_type": Role.RoleType.SYSTEM,
            "permissions": list(TOOL_PERMISSION_KEYS),
            "created_by": saas_user,
        },
    )
    RoleAssignment.objects.get_or_create(
        user=saas_user,
        role=role,
        organization=None,
        defaults={"assigned_by": saas_user},
    )
    saas_client = APIClient()
    saas_client.force_authenticate(user=saas_user)

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
    return organization, org_client, saas_client


@pytest.mark.django_db
def test_list_tools(tool_context):
    organization, client, _ = tool_context
    response = client.get(reverse("tool-list", kwargs={"organization_uuid": organization.uuid}))
    assert response.status_code == status.HTTP_200_OK
    assert response.json()


@pytest.mark.django_db
def test_enable_tool(tool_context):
    organization, _, client = tool_context
    enable_url = reverse(
        "organization-tools-enable",
        kwargs={"organization_uuid": organization.uuid, "tool_key": "calculator"},
    )
    response = client.post(enable_url)
    assert response.status_code == status.HTTP_200_OK
    assert OrganizationEnabledTool.objects.filter(organization=organization, tool_key="calculator").exists()


@pytest.mark.django_db
def test_tool_limit(tool_context):
    organization, _, client = tool_context
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
    assert response.json()["code"] == "MAX_TOOLS_EXCEEDED"
