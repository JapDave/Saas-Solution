import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.organizations.tests.factories import OrganizationFactory
from apps.roles.constants import (
    ROLE_ORGANIZATION_ADMINISTRATOR,
    ROLE_ORGANIZATION_OWNER,
)
from apps.roles.models import Role, RoleAssignment
from apps.users.tests.factories import UserFactory, UserOrganizationFactory


@pytest.fixture
def api_client():
    return APIClient()


def _bootstrap_roles(*, organization, actor):
    owner_role = Role.objects.create(
        organization=organization,
        name=ROLE_ORGANIZATION_OWNER,
        description="Owner",
        permissions=["organizations:assign_owner"],
        role_type=Role.RoleType.PREDEFINED_CUSTOM,
        is_active=True,
        created_by=actor,
    )
    admin_role = Role.objects.create(
        organization=organization,
        name=ROLE_ORGANIZATION_ADMINISTRATOR,
        description="Admin",
        permissions=["organizations:update"],
        role_type=Role.RoleType.PREDEFINED_CUSTOM,
        is_active=True,
        created_by=actor,
    )
    RoleAssignment.objects.create(
        organization=organization,
        user=actor,
        role=owner_role,
        assigned_by=actor,
    )
    RoleAssignment.objects.create(
        organization=organization,
        user=actor,
        role=admin_role,
        assigned_by=actor,
    )
    return owner_role, admin_role


@pytest.mark.django_db
def test_assign_role_success(api_client):
    organization = OrganizationFactory()
    actor = organization.created_by
    UserOrganizationFactory(user=actor, organization=organization)
    _bootstrap_roles(organization=organization, actor=actor)

    target_user = UserFactory()
    UserOrganizationFactory(user=target_user, organization=organization)
    custom_role = Role.objects.create(
        organization=organization,
        name="Billing Specialist",
        description="Billing role",
        permissions=["billing:view"],
        role_type=Role.RoleType.USER_CUSTOM,
        is_active=True,
        created_by=actor,
    )

    client = api_client
    client.force_authenticate(actor)
    url = reverse(
        "role-assignment-list",
        kwargs={"organization_uuid": str(organization.uuid)},
    )
    response = client.post(
        url,
        {"user": str(target_user.uuid), "role": str(custom_role.uuid)},
        format="json",
    )

    assert response.status_code == 201
    assert RoleAssignment.objects.filter(
        organization=organization,
        user=target_user,
        role=custom_role,
        deleted_at__isnull=True,
    ).exists()


@pytest.mark.django_db
def test_assign_role_rejects_non_member(api_client):
    organization = OrganizationFactory()
    actor = organization.created_by
    UserOrganizationFactory(user=actor, organization=organization)
    _bootstrap_roles(organization=organization, actor=actor)

    outsider = UserFactory()
    role = Role.objects.create(
        organization=organization,
        name="Observer",
        description="Observer",
        permissions=["organizations:read"],
        role_type=Role.RoleType.USER_CUSTOM,
        is_active=True,
        created_by=actor,
    )

    client = api_client
    client.force_authenticate(actor)
    url = reverse(
        "role-assignment-list",
        kwargs={"organization_uuid": str(organization.uuid)},
    )
    response = client.post(
        url,
        {"user": str(outsider.uuid), "role": str(role.uuid)},
        format="json",
    )

    assert response.status_code == 400
    assert "user" in response.data


@pytest.mark.django_db
def test_remove_last_owner_is_blocked(api_client):
    organization = OrganizationFactory()
    actor = organization.created_by
    UserOrganizationFactory(user=actor, organization=organization)
    owner_role, _ = _bootstrap_roles(organization=organization, actor=actor)

    client = api_client
    client.force_authenticate(actor)

    assignment = RoleAssignment.objects.get(
        organization=organization,
        user=actor,
        role=owner_role,
    )
    url = reverse(
        "role-assignment-detail",
        kwargs={
            "organization_uuid": str(organization.uuid),
            "uuid": str(assignment.uuid),
        },
    )
    response = client.delete(url)

    assert response.status_code == 400
    assert "owner" in str(response.data).lower()


@pytest.mark.django_db
def test_remove_owner_when_multiple_remaining(api_client):
    organization = OrganizationFactory()
    actor = organization.created_by
    UserOrganizationFactory(user=actor, organization=organization)
    owner_role, _ = _bootstrap_roles(organization=organization, actor=actor)

    second_owner = UserFactory()
    UserOrganizationFactory(user=second_owner, organization=organization)
    RoleAssignment.objects.create(
        organization=organization,
        user=second_owner,
        role=owner_role,
        assigned_by=actor,
    )

    client = api_client
    client.force_authenticate(actor)

    assignment = RoleAssignment.objects.get(
        organization=organization,
        user=second_owner,
        role=owner_role,
    )
    url = reverse(
        "role-assignment-detail",
        kwargs={
            "organization_uuid": str(organization.uuid),
            "uuid": str(assignment.uuid),
        },
    )
    response = client.delete(url)

    assert response.status_code == 204
    assignment.refresh_from_db()
    assert assignment.deleted_at is not None
