import pytest
from django.urls import reverse

from apps.accounts.tests.factories import AccountFactory
from apps.organizations.tests.factories import OrganizationFactory
from apps.users.models import UserOrganization
from apps.users.tests.factories import UserFactory


@pytest.mark.django_db
class TestUserCreation:
    def test_superadmin_can_create_user_with_membership(self, superadmin_client, primary_account_alpha_organization):
        url = reverse("users-list")
        role = Role.objects.create(
            organization=primary_account_alpha_organization,
            name="Org Admin",
            description="Org administrator",
            permissions=["user:create", "user:manage_membership"],
            role_type=Role.RoleType.USER_CUSTOM,
            is_active=True,
            created_by=primary_account_alpha_organization.created_by,
        )
        payload = {
            "email": "new.user@example.com",
            "password": "SuperSecure1",
            "full_name": "New User",
            "memberships": [
                {
                    "organization": primary_account_alpha_organization.id,
                    "permissions": ["user:create", "user:manage_membership"],
                    "roles": [str(role.uuid)],
                }
            ],
        }
        response = superadmin_client.post(url, payload, format="json")
        assert response.status_code == 201
        body = response.json()
        assert body["email"] == "new.user@example.com"
        assert body["is_active"] is True
        assert len(body["memberships"]) == 1
        assert body["memberships"][0]["roles"][0]["uuid"] == str(role.uuid)
        membership = UserOrganization.objects.get(user__email="new.user@example.com")
        assert membership.organization_id == primary_account_alpha_organization.id
        assert set(membership.permission_keys) == {"user:create", "user:manage_membership"}
        assert RoleAssignment.objects.filter(
            organization=primary_account_alpha_organization,
            user__email="new.user@example.com",
            role=role,
            deleted_at__isnull=True,
        ).exists()

    def test_create_user_requires_membership(self, superadmin_client):
        url = reverse("users-list")
        payload = {
            "email": "isolated.user@example.com",
            "password": "SecurePass8",
            "full_name": "Isolated User",
            "memberships": [],
        }
        response = superadmin_client.post(url, payload, format="json")
        assert response.status_code == 400
        assert response.json()["code"] == "INVALID_USER_DATA"


@pytest.mark.django_db
class TestUserStatus:
    def test_cannot_deactivate_account_owner(self, superadmin_client):
        owner = UserFactory(email="owner1@example.com", full_name="Owner User")
        account = AccountFactory(created_by=owner, updated_by=owner)
        OrganizationFactory(account=account, created_by=owner, updated_by=owner)
        url = reverse("users-status-change", kwargs={"uuid": str(owner.uuid)})
        response = superadmin_client.post(url, {"is_active": False}, format="json")
        assert response.status_code == 400
        assert response.json()["code"] == "CANNOT_DEACTIVATE_OWNER"


@pytest.mark.django_db
class TestMembershipManagement:
    def test_add_and_remove_membership(self, superadmin_client, primary_account_alpha_organization, secondary_account_charlie_organization):
        url = reverse("users-list")
        primary_role = Role.objects.create(
            organization=primary_account_alpha_organization,
            name="Primary Admin",
            description="Primary organization administrator",
            permissions=["user:manage_membership"],
            role_type=Role.RoleType.USER_CUSTOM,
            is_active=True,
            created_by=primary_account_alpha_organization.created_by,
        )
        secondary_role = Role.objects.create(
            organization=secondary_account_charlie_organization,
            name="Secondary Viewer",
            description="Secondary organization viewer",
            permissions=["user:view"],
            role_type=Role.RoleType.USER_CUSTOM,
            is_active=True,
            created_by=secondary_account_charlie_organization.created_by,
        )
        payload = {
            "email": "membership.user@example.com",
            "password": "SecurePass8",
            "full_name": "Membership User",
            "memberships": [
                {
                    "organization": primary_account_alpha_organization.id,
                    "permissions": ["user:manage_membership"],
                    "roles": [str(primary_role.uuid)],
                }
            ],
        }
        create_response = superadmin_client.post(url, payload, format="json")
        assert create_response.status_code == 201
        user_uuid = create_response.json()["uuid"]
        assert RoleAssignment.objects.filter(
            organization=primary_account_alpha_organization,
            user__uuid=user_uuid,
            role=primary_role,
            deleted_at__isnull=True,
        ).exists()

        add_url = reverse("users-add-membership", kwargs={"uuid": user_uuid})
        add_payload = {
            "organization": secondary_account_charlie_organization.id,
            "permissions": ["user:view"],
            "roles": [str(secondary_role.uuid)],
        }
        add_response = superadmin_client.post(add_url, add_payload, format="json")
        assert add_response.status_code == 201
        assert UserOrganization.objects.filter(
            user__uuid=user_uuid, organization=secondary_account_charlie_organization
        ).exists()
        assert RoleAssignment.objects.filter(
            organization=secondary_account_charlie_organization,
            user__uuid=user_uuid,
            role=secondary_role,
            deleted_at__isnull=True,
        ).exists()

        remove_url = reverse(
            "users-remove-membership",
            kwargs={"uuid": user_uuid, "organization_id": secondary_account_charlie_organization.id},
        )
        remove_response = superadmin_client.delete(remove_url, format="json")
        assert remove_response.status_code == 204
        assert not UserOrganization.objects.filter(
            user__uuid=user_uuid,
            organization=secondary_account_charlie_organization,
            deleted_at__isnull=True,
        ).exists()
        assert not RoleAssignment.objects.filter(
            organization=secondary_account_charlie_organization,
            user__uuid=user_uuid,
            role=secondary_role,
            deleted_at__isnull=True,
        ).exists()

        add_url = reverse("users-add-membership", kwargs={"uuid": user_uuid})
        add_payload = {"organization": secondary_account_charlie_organization.id, "permissions": ["user:view"]}
        add_response = superadmin_client.post(add_url, add_payload, format="json")
        assert add_response.status_code == 201
        assert UserOrganization.objects.filter(
            user__uuid=user_uuid, organization=secondary_account_charlie_organization
        ).exists()

        remove_url = reverse(
            "users-remove-membership",
            kwargs={"uuid": user_uuid, "organization_id": secondary_account_charlie_organization.id},
        )
        remove_response = superadmin_client.delete(remove_url, format="json")
        assert remove_response.status_code == 204
        assert not UserOrganization.objects.filter(
            user__uuid=user_uuid,
            organization=secondary_account_charlie_organization,
            deleted_at__isnull=True,
        ).exists()


@pytest.mark.django_db
class TestUserListing:
    def test_account_owner_sees_users_in_owned_account(self, api_client):
        owner = UserFactory(email="account.owner@example.com", full_name="Account Owner")
        other_user = UserFactory(email="other.user@example.com", full_name="Other User")
        account = AccountFactory(created_by=owner, updated_by=owner)
        org = OrganizationFactory(account=account, created_by=owner, updated_by=owner)
        role = Role.objects.create(
            organization=org,
            name="Org Reader",
            description="Organization reader",
            permissions=["user:read"],
            role_type=Role.RoleType.USER_CUSTOM,
            is_active=True,
            created_by=owner,
        )
        owner_membership = UserOrganization.objects.create(
            user=owner,
            organization=org,
            assigned_by=owner,
            permission_keys=["user:read"],
        )
        other_membership = UserOrganization.objects.create(
            user=other_user,
            organization=org,
            assigned_by=owner,
            permission_keys=["user:read"],
        )
        RoleAssignment.objects.create(
            organization=org,
            user=owner,
            role=role,
            assigned_by=owner_membership.assigned_by,
        )
        RoleAssignment.objects.create(
            organization=org,
            user=other_user,
            role=role,
            assigned_by=owner,
        )

        client = api_client()
        client.force_authenticate(user=owner)
        url = reverse("users-list")
        response = client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data["count"] >= 1
        emails = {item["email"] for item in data["results"]}
        assert "other.user@example.com" in emails


@pytest.mark.django_db
class TestSessionContext:
    def test_switch_organization(self, regular_client, regular_user):
        org = OrganizationFactory(account__created_by=regular_user, created_by=regular_user, updated_by=regular_user)
        role = Role.objects.create(
            organization=org,
            name="Org Viewer",
            description="Organization viewer",
            permissions=["user:view"],
            role_type=Role.RoleType.USER_CUSTOM,
            is_active=True,
            created_by=regular_user,
        )
        membership = UserOrganization.objects.create(
            user=regular_user,
            organization=org,
            assigned_by=regular_user,
            permission_keys=["user:view"],
        )
        RoleAssignment.objects.create(
            organization=org,
            user=regular_user,
            role=role,
            assigned_by=membership.assigned_by,
        )
        url = reverse("users-switch-organization")
        response = regular_client.post(url, {"organization": org.id}, format="json")
        assert response.status_code == 200
        assert regular_client.session["active_organization_id"] == org.id



