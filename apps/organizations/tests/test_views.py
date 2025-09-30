import uuid

import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestOrganizationPermissions:
    """Permission and scoping scenarios for organization endpoints."""

    def test_staff_scope_crud(self, manager_client_assigned_to_primary_account, primary_account_alpha_organization, secondary_account_charlie_organization, primary_account, secondary_account):
        list_url = reverse("organizations-list")
        response = manager_client_assigned_to_primary_account.get(list_url)
        assert response.status_code == 200
        ids = {item["id"] for item in response.json()["results"]}
        assert primary_account_alpha_organization.id in ids
        assert secondary_account_charlie_organization.id not in ids

        create_payload = {"account": primary_account.id, "name": "HQ"}
        assert manager_client_assigned_to_primary_account.post(list_url, create_payload, format="json").status_code == 201

        forbidden_payload = {"account": secondary_account.id, "name": "OtherHQ"}
        forbidden = manager_client_assigned_to_primary_account.post(list_url, forbidden_payload, format="json")
        assert forbidden.status_code == 403
        assert forbidden.json().get("code") == "INSUFFICIENT_PERMISSIONS"

        detail_url = reverse("organizations-detail", kwargs={"uuid": str(primary_account_alpha_organization.uuid)})
        update = manager_client_assigned_to_primary_account.patch(detail_url, {"description": "scoped"}, format="json")
        assert update.status_code == 200
        assert update.json()["description"] == "scoped"

        other_detail = reverse("organizations-detail", kwargs={"uuid": str(secondary_account_charlie_organization.uuid)})
        out_of_scope = manager_client_assigned_to_primary_account.patch(other_detail, {"description": "nope"}, format="json")
        assert out_of_scope.status_code == 404
        assert out_of_scope.json().get("code") == "ORGANIZATION_NOT_FOUND"

        assert manager_client_assigned_to_primary_account.delete(detail_url).status_code == 204

        delete_missing = manager_client_assigned_to_primary_account.delete(other_detail)
        assert delete_missing.status_code == 404
        assert delete_missing.json().get("code") == "ORGANIZATION_NOT_FOUND"

    def test_staff_no_assignments(self, manager_client_with_no_assignments, primary_account):
        list_url = reverse("organizations-list")
        response = manager_client_with_no_assignments.get(list_url)
        assert response.status_code == 200
        assert response.json()["results"] == []

        create_payload = {"account": primary_account.id, "name": "Nope"}
        create_response = manager_client_with_no_assignments.post(list_url, create_payload, format="json")
        assert create_response.status_code == 403
        assert create_response.json().get("code") == "INSUFFICIENT_PERMISSIONS"

    def test_account_owner_scope(self, regular_client, account_owned_by_regular_user, organization_owned_by_regular_user, primary_account, primary_account_alpha_organization):
        list_url = reverse("organizations-list")

        list_response = regular_client.get(list_url)
        assert list_response.status_code == 200
        ids = {item["id"] for item in list_response.json()["results"]}
        assert organization_owned_by_regular_user.id in ids
        assert primary_account_alpha_organization.id not in ids

        owned_payload = {"account": account_owned_by_regular_user.id, "name": "UHQ"}
        owned_response = regular_client.post(list_url, owned_payload, format="json")
        assert owned_response.status_code == 201

        other_payload = {"account": primary_account.id, "name": "Nope"}
        other_response = regular_client.post(list_url, other_payload, format="json")
        assert other_response.status_code == 403
        assert other_response.json().get("code") == "INSUFFICIENT_PERMISSIONS"

        detail_url = reverse("organizations-detail", kwargs={"uuid": str(organization_owned_by_regular_user.uuid)})
        patch_owned = regular_client.patch(detail_url, {"description": "mine"}, format="json")
        assert patch_owned.status_code == 200
        assert patch_owned.json()["description"] == "mine"

        other_detail = reverse("organizations-detail", kwargs={"uuid": str(primary_account_alpha_organization.uuid)})
        out_of_scope = regular_client.patch(other_detail, {"description": "nope"}, format="json")
        assert out_of_scope.status_code == 404
        assert out_of_scope.json().get("code") == "ORGANIZATION_NOT_FOUND"


@pytest.mark.django_db
class TestOrganizationCreate:
    """Creation flows and validation for organization endpoints."""

    def test_admin_create_min(self, admin_client, primary_account):
        url = reverse("organizations-list")
        response = admin_client.post(url, {"account": primary_account.id, "name": "HQ"}, format="json")
        assert response.status_code == 201
        body = response.json()
        assert body["account"] == primary_account.id
        assert body["name"] == "HQ"
        assert body["is_active"] is True
        assert body.get("deleted_at") is None

    def test_create_validation(self, admin_client, primary_account):
        url = reverse("organizations-list")

        missing_account = admin_client.post(url, {"name": "HQ"}, format="json")
        assert missing_account.status_code == 400
        assert missing_account.json().get("code") == "INVALID_ORGANIZATION_DATA"

        missing_name = admin_client.post(url, {"account": primary_account.id}, format="json")
        assert missing_name.status_code == 400
        assert missing_name.json().get("code") == "INVALID_ORGANIZATION_DATA"

        wrong_type = admin_client.post(url, {"account": primary_account.id, "name": 123}, format="json")
        data = wrong_type.json()
        assert wrong_type.status_code == 400
        assert data.get("code") == "INVALID_ORGANIZATION_DATA"
        assert "name" in data.get("errors", {})

    def test_create_uniques_per_account(self, admin_client, primary_account, secondary_account):
        url = reverse("organizations-list")

        assert (
            admin_client.post(url, {"account": primary_account.id, "name": "North"}, format="json").status_code == 201
        )

        duplicate_same_account = admin_client.post(
            url,
            {"account": primary_account.id, "name": "north"},
            format="json",
        )
        assert duplicate_same_account.status_code == 409
        assert duplicate_same_account.json().get("code") == "ORGANIZATION_NAME_EXISTS"

        other_account = admin_client.post(url, {"account": secondary_account.id, "name": "north"}, format="json")
        assert other_account.status_code == 201


@pytest.mark.django_db
class TestOrganizationRead:
    """Listing, filtering, and retrieval for organizations."""

    def test_list_and_filters(self, admin_client, primary_account_alpha_organization, primary_account_bravo_organization, secondary_account_charlie_organization):
        url = reverse("organizations-list")
        response = admin_client.get(url)
        assert response.status_code == 200
        ids = {item["id"] for item in response.json()["results"]}
        assert {primary_account_alpha_organization.id, primary_account_bravo_organization.id, secondary_account_charlie_organization.id}.issubset(ids)

        assert admin_client.get(url + "?ordering=name").status_code == 200
        assert admin_client.get(url + "?is_active=true").status_code == 200
        assert admin_client.get(url + f"?account={primary_account_alpha_organization.account_id}").status_code == 200

        bad_page = admin_client.get(url + "?page_size=-1")
        payload = bad_page.json()
        assert bad_page.status_code == 400
        assert "page_size" in payload.get("errors", {})

    def test_get(self, admin_client, primary_account_alpha_organization):
        url = reverse("organizations-detail", kwargs={"uuid": str(primary_account_alpha_organization.uuid)})
        response = admin_client.get(url)
        assert response.status_code == 200
        assert response.json()["id"] == primary_account_alpha_organization.id


@pytest.mark.django_db
class TestOrganizationUpdateDelete:
    """Update and deletion behaviour for organizations."""

    def test_update_ok(self, admin_client, primary_account_alpha_organization):
        url = reverse("organizations-detail", kwargs={"uuid": str(primary_account_alpha_organization.uuid)})
        payload = {
            "account": primary_account_alpha_organization.account_id,
            "name": "Alpha HQ",
            "description": "Main office",
            "logo_url": "",
            "is_active": True,
        }
        response = admin_client.put(url, payload, format="json")
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Alpha HQ"
        assert body["description"] == "Main office"
        assert body["is_active"] is True

    def test_update_dup(self, admin_client, primary_account_alpha_organization, primary_account_bravo_organization):
        url = reverse("organizations-detail", kwargs={"uuid": str(primary_account_bravo_organization.uuid)})
        payload = {
            "account": primary_account_bravo_organization.account_id,
            "name": primary_account_alpha_organization.name,
            "description": "",
            "logo_url": "",
            "is_active": True,
        }
        response = admin_client.put(url, payload, format="json")
        assert response.status_code == 409
        assert response.json().get("code") == "ORGANIZATION_NAME_EXISTS"

    def test_patch_validation(self, admin_client, primary_account_alpha_organization):
        url = reverse("organizations-detail", kwargs={"uuid": str(primary_account_alpha_organization.uuid)})

        invalid = admin_client.patch(url, {"name": 123}, format="json")
        data = invalid.json()
        assert invalid.status_code == 400
        assert data.get("code") == "INVALID_ORGANIZATION_DATA"
        assert "name" in data.get("errors", {})

        valid = admin_client.patch(url, {"description": "short"}, format="json")
        assert valid.status_code == 200
        assert valid.json()["description"] == "short"

    def test_update_404(self, admin_client, primary_account):
        url = reverse("organizations-detail", kwargs={"uuid": str(uuid.uuid4())})
        payload = {
            "account": primary_account.id,
            "name": "X",
            "description": "",
            "logo_url": "",
            "is_active": True,
        }
        response = admin_client.put(url, payload, format="json")
        assert response.status_code == 404
        assert response.json().get("code") == "ORGANIZATION_NOT_FOUND"

    def test_delete(self, admin_client, primary_account_alpha_organization):
        url = reverse("organizations-detail", kwargs={"uuid": str(primary_account_alpha_organization.uuid)})
        assert admin_client.delete(url).status_code == 204

        follow_up = admin_client.get(url)
        assert follow_up.status_code == 404
        if follow_up.headers.get("Content-Type", "").startswith("application/json"):
            payload = follow_up.json()
            if isinstance(payload, dict) and "code" in payload:
                assert payload["code"] == "ORGANIZATION_NOT_FOUND"

    def test_delete_404(self, admin_client):
        url = reverse("organizations-detail", kwargs={"uuid": str(uuid.uuid4())})
        response = admin_client.delete(url)
        assert response.status_code == 404
        assert response.json().get("code") == "ORGANIZATION_NOT_FOUND"
