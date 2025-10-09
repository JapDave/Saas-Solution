import pytest
from django.urls import reverse

from apps.accounts.tests.factories import AccountFactory
from apps.organizations.tests.factories import OrganizationFactory
from apps.teams.models import TeamMember
from apps.teams.tests.factories import TeamFactory, TeamMemberFactory
from apps.users.tests.factories import UserFactory, UserOrganizationFactory


@pytest.mark.django_db
class TestTeamAdminFlows:
    def test_admin_crud(self, admin_client):
        organization = OrganizationFactory()
        list_url = reverse("team-list")
        create_response = admin_client.post(
            list_url,
            {"organization": organization.id, "name": "Engineering"},
            format="json",
        )
        assert create_response.status_code == 201
        team_uuid = create_response.json()["uuid"]

        list_response = admin_client.get(list_url)
        assert list_response.status_code == 200
        assert any(item["name"] == "Engineering" for item in list_response.json()["results"])

        detail_url = reverse("team-detail", kwargs={"uuid": team_uuid})
        get_response = admin_client.get(detail_url)
        assert get_response.status_code == 200
        assert get_response.json()["name"] == "Engineering"

        patch_response = admin_client.patch(detail_url, {"description": "Core eng"}, format="json")
        assert patch_response.status_code == 200
        assert patch_response.json()["description"] == "Core eng"

        delete_response = admin_client.delete(detail_url)
        assert delete_response.status_code == 204

        follow_response = admin_client.get(detail_url)
        assert follow_response.status_code == 404
        assert follow_response.json().get("code") == "TEAM_NOT_FOUND"

    def test_manage_members(self, admin_client):
        team = TeamFactory()
        target = UserFactory()
        UserOrganizationFactory(user=target, organization=team.organization)
        members_url = reverse("team-members", kwargs={"uuid": str(team.uuid)})

        add_response = admin_client.post(members_url, {"user": str(target.uuid)}, format="json")
        assert add_response.status_code == 201
        assert TeamMember.objects.filter(team=team, user=target).exists()

        remove_url = reverse(
            "team-remove-member",
            kwargs={"uuid": str(team.uuid), "user_uuid": str(target.uuid)},
        )
        remove_response = admin_client.delete(remove_url)
        assert remove_response.status_code == 204
        membership = TeamMember.all_objects.get(team=team, user=target)
        assert membership.deleted_at is not None


@pytest.mark.django_db
class TestTeamManagerScope:
    def test_manager_assigned_accounts(self, manager_client_assigned_to_primary_account, primary_account):
        organization = OrganizationFactory(account=primary_account)
        other_account = AccountFactory()
        other_org = OrganizationFactory(account=other_account)
        team_in_scope = TeamFactory(organization=organization)
        TeamFactory(organization=other_org)

        list_url = reverse("team-list")
        response = manager_client_assigned_to_primary_account.get(list_url)
        assert response.status_code == 200
        results = response.json()["results"]
        ids = {item["id"] for item in results}
        assert team_in_scope.id in ids
        assert len(results) == 1

        create_payload = {"organization": other_org.id, "name": "Blocked"}
        blocked = manager_client_assigned_to_primary_account.post(list_url, create_payload, format="json")
        assert blocked.status_code == 403
        assert blocked.json().get("code") == "INSUFFICIENT_PERMISSIONS"

    def test_manager_member_management_requires_scope(self, manager_client_assigned_to_primary_account, primary_account):
        organization = OrganizationFactory(account=primary_account)
        team = TeamFactory(organization=organization)
        target = UserFactory()
        UserOrganizationFactory(user=target, organization=organization)
        members_url = reverse("team-members", kwargs={"uuid": str(team.uuid)})
        response = manager_client_assigned_to_primary_account.post(members_url, {"user": str(target.uuid)}, format="json")
        assert response.status_code == 201


@pytest.mark.django_db
class TestTeamMemberAccess:
    def test_member_can_view_team(self, regular_client, regular_user):
        team = TeamFactory()
        UserOrganizationFactory(user=regular_user, organization=team.organization)
        TeamMemberFactory(team=team, user=regular_user)
        detail_url = reverse("team-detail", kwargs={"uuid": str(team.uuid)})
        response = regular_client.get(detail_url)
        assert response.status_code == 200

    def test_non_member_forbidden(self, regular_client, regular_user):
        team = TeamFactory()
        detail_url = reverse("team-detail", kwargs={"uuid": str(team.uuid)})
        response = regular_client.get(detail_url)
        assert response.status_code in {403, 404}


@pytest.mark.django_db
class TestTeamListPagination:
    def test_invalid_page_size(self, admin_client):
        list_url = reverse("team-list")
        response = admin_client.get(list_url + "?page_size=0")
        assert response.status_code == 400
        payload = response.json()
        assert "page_size" in payload.get("errors", {})


__all__ = []
