import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

from apps.users.models import UserOrganization
from apps.organizations.models import Organization
from apps.roles.models import Role, RoleAssignment


@pytest.mark.django_db
def test_user_account_organization_flow(superadmin_client, superadmin_user, manager_user):
    """Exercise the full provisioning flow from superadmin down to member context switching."""

    accounts_url = reverse("account-list")
    organizations_url = reverse("organization-list")

    alpha_payload = {
        "name": "Alpha Corp",
        "description": "",
        "contact_email": "alpha-owner@example.com",
    }
    bravo_payload = {
        "name": "Bravo Corp",
        "description": "",
        "contact_email": "bravo-owner@example.com",
    }

    alpha_response = superadmin_client.post(accounts_url, alpha_payload, format="json")
    bravo_response = superadmin_client.post(accounts_url, bravo_payload, format="json")
    assert alpha_response.status_code == 201
    assert bravo_response.status_code == 201
    alpha_account_id = alpha_response.data["id"]
    bravo_account_id = bravo_response.data["id"]

    alpha_hq_resp = superadmin_client.post(
        organizations_url,
        {"account": alpha_account_id, "name": "Alpha HQ"},
        format="json",
    )
    alpha_labs_resp = superadmin_client.post(
        organizations_url,
        {"account": alpha_account_id, "name": "Alpha Labs"},
        format="json",
    )
    bravo_rd_resp = superadmin_client.post(
        organizations_url,
        {"account": bravo_account_id, "name": "Bravo R&D"},
        format="json",
    )
    assert alpha_hq_resp.status_code == 201
    assert alpha_labs_resp.status_code == 201
    assert bravo_rd_resp.status_code == 201

    alpha_hq_id = alpha_hq_resp.data["id"]
    alpha_labs_id = alpha_labs_resp.data["id"]
    bravo_rd_id = bravo_rd_resp.data["id"]

    alpha_hq_org = Organization.objects.get(id=alpha_hq_id)
    alpha_labs_org = Organization.objects.get(id=alpha_labs_id)
    role_hq = Role.objects.create(
        organization=alpha_hq_org,
        name="Alpha HQ Member",
        description="Alpha HQ member",
        permissions=["user:read"],
        role_type=Role.RoleType.USER_CUSTOM,
        is_active=True,
        created_by=alpha_hq_org.created_by,
    )
    role_labs = Role.objects.create(
        organization=alpha_labs_org,
        name="Alpha Labs Editor",
        description="Alpha Labs editor",
        permissions=["user:read", "user:update"],
        role_type=Role.RoleType.USER_CUSTOM,
        is_active=True,
        created_by=alpha_labs_org.created_by,
    )

    manager_client = APIClient()
    manager_user.get_assigned_account_ids = lambda: [alpha_account_id]
    manager_client.force_authenticate(user=manager_user)

    manager_accounts_resp = manager_client.get(accounts_url)
    assert manager_accounts_resp.status_code == 200
    assert manager_accounts_resp.data["count"] == 1

    forbidden_org_resp = manager_client.post(
        organizations_url,
        {"account": bravo_account_id, "name": "Bravo Secure"},
        format="json",
    )
    assert forbidden_org_resp.status_code == 403

    users_url = reverse("user-list")
    create_user_resp = manager_client.post(
        users_url,
        {
            "email": "member@example.com",
            "password": "StrongPass123",
            "full_name": "Org Member",
            "memberships": [
                {
                    "organization": alpha_hq_id,
                    "permissions": ["user:read"],
                    "roles": [str(role_hq.uuid)],
                },
                {
                    "organization": alpha_labs_id,
                    "permissions": ["user:read", "user:update"],
                    "roles": [str(role_labs.uuid)],
                },
            ],
        },
        format="json",
    )
    assert create_user_resp.status_code == 201
    member_uuid = create_user_resp.data["uuid"]
    member_id = create_user_resp.data["id"]

    assert RoleAssignment.objects.filter(
        organization_id=alpha_hq_id,
        user__uuid=member_uuid,
        role=role_hq,
        deleted_at__isnull=True,
    ).exists()
    assert RoleAssignment.objects.filter(
        organization_id=alpha_labs_id,
        user__uuid=member_uuid,
        role=role_labs,
        deleted_at__isnull=True,
    ).exists()

    duplicate_membership_resp = manager_client.post(
        reverse("user-add-membership", kwargs={"uuid": member_uuid}),
        {"organization": bravo_rd_id, "permissions": ["user:read"]},
        format="json",
    )
    assert duplicate_membership_resp.status_code == 403

    member = get_user_model().objects.get(id=member_id)
    member_client = APIClient()
    member_client.force_authenticate(user=member)

    member_orgs_resp = member_client.get(organizations_url)
    assert member_orgs_resp.status_code == 200
    assert member_orgs_resp.data["count"] == 2
    returned_ids = {item["id"] for item in member_orgs_resp.data["results"]}
    assert returned_ids == {alpha_hq_id, alpha_labs_id}

    switch_url = reverse("user-switch-organization")
    switch_resp = member_client.post(
        switch_url,
        {"organization": alpha_labs_id},
        format="json",
    )
    assert switch_resp.status_code == 200
    assert member_client.session["active_organization_id"] == alpha_labs_id

    forbidden_switch_resp = member_client.post(
        switch_url,
        {"organization": bravo_rd_id},
        format="json",
    )
    assert forbidden_switch_resp.status_code == 403

    user_memberships = UserOrganization.objects.filter(user=member)
    assert user_memberships.count() == 2




