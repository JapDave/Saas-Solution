import uuid

import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestAccountPermissions:
    """Permissions and ownership scenarios for account endpoints."""

    def test_staff_view(self, manager_client, primary_account, secondary_account):
        url = reverse("account-list")
        response = manager_client.get(url)
        assert response.status_code == 200

        detail_url = reverse("account-detail", kwargs={"uuid": str(primary_account.uuid)})
        detail_response = manager_client.get(detail_url)
        assert detail_response.status_code == 200

        create_payload = {"name": "X", "contact_email": "x@x.com"}
        create_response = manager_client.post(url, create_payload, format="json")
        assert create_response.status_code == 403
        assert create_response.json().get("code") == "INSUFFICIENT_PERMISSIONS"

        update_payload = {
            "name": "N",
            "description": "",
            "contact_email": "n@n.com",
            "is_active": True,
        }
        update_response = manager_client.put(detail_url, update_payload, format="json")
        assert update_response.status_code == 403
        assert update_response.json().get("code") == "INSUFFICIENT_PERMISSIONS"

        patch_response = manager_client.patch(detail_url, {"description": "nope"}, format="json")
        assert patch_response.status_code == 403
        assert patch_response.json().get("code") == "INSUFFICIENT_PERMISSIONS"

        delete_response = manager_client.delete(detail_url)
        assert delete_response.status_code == 403
        assert delete_response.json().get("code") == "INSUFFICIENT_PERMISSIONS"

    def test_user_owner_update(self, regular_client, account_owned_by_regular_user):
        list_url = reverse("account-list")

        list_response = regular_client.get(list_url)
        assert list_response.status_code == 403
        assert list_response.json().get("code") == "INSUFFICIENT_PERMISSIONS"

        create_payload = {"name": "Own", "contact_email": "own@me.com"}
        create_response = regular_client.post(list_url, create_payload, format="json")
        assert create_response.status_code == 403
        assert create_response.json().get("code") == "INSUFFICIENT_PERMISSIONS"

        detail_url = reverse("account-detail", kwargs={"uuid": str(account_owned_by_regular_user.uuid)})
        patch_response = regular_client.patch(detail_url, {"description": "mine"}, format="json")
        assert patch_response.status_code == 200
        assert patch_response.json()["description"] == "mine"


@pytest.mark.django_db
class TestAccountCreate:
    """Create flows and validation for accounts."""

    def test_admin_create(self, admin_client):
        url = reverse("account-list")
        response = admin_client.post(
            url,
            {"name": "Foobar", "contact_email": "admin@foobar.com"},
            format="json",
        )
        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Foobar"
        assert body["contact_email"] == "admin@foobar.com"
        assert body["is_active"] is True
        assert body.get("deleted_at") is None

    def test_create_validation(self, admin_client):
        url = reverse("account-list")

        missing_name = admin_client.post(url, {"contact_email": "x@y.com"}, format="json")
        assert missing_name.status_code == 400
        assert missing_name.json().get("code") == "INVALID_ACCOUNT_DATA"

        missing_email = admin_client.post(url, {"name": "X"}, format="json")
        assert missing_email.status_code == 400
        assert missing_email.json().get("code") == "INVALID_ACCOUNT_DATA"

        wrong_type = admin_client.post(
            url,
            {"name": 123, "contact_email": "x@y.com"},
            format="json",
        )
        data = wrong_type.json()
        assert wrong_type.status_code == 400
        assert data.get("code") == "INVALID_ACCOUNT_DATA"
        assert "name" in data.get("errors", {})

    def test_create_uniques(self, admin_client):
        url = reverse("account-list")
        assert (
            admin_client.post(url, {"name": "Acme", "contact_email": "one@acme.com"}, format="json").status_code
            == 201
        )

        dup_name = admin_client.post(url, {"name": "acme", "contact_email": "two@acme.com"}, format="json")
        assert dup_name.status_code == 400
        assert dup_name.json().get("code") in {"ACCOUNT_NAME_EXISTS", "INVALID_ACCOUNT_DATA"}

        dup_email = admin_client.post(url, {"name": "NewCo", "contact_email": "ONE@ACME.COM"}, format="json")
        assert dup_email.status_code == 400
        assert dup_email.json().get("code") in {"CONTACT_EMAIL_EXISTS", "INVALID_ACCOUNT_DATA"}


@pytest.mark.django_db
class TestAccountRead:
    """Listing and retrieval behaviour for accounts."""

    def test_list(self, admin_client, primary_account, secondary_account):
        url = reverse("account-list")
        response = admin_client.get(url)
        assert response.status_code == 200
        ids = {item["id"] for item in response.json()["results"]}
        assert primary_account.id in ids and secondary_account.id in ids

        assert admin_client.get(url + "?ordering=name").status_code == 200
        assert admin_client.get(url + "?is_active=true").status_code == 200

    def test_get(self, admin_client, primary_account):
        url = reverse("account-detail", kwargs={"uuid": str(primary_account.uuid)})
        response = admin_client.get(url)
        assert response.status_code == 200
        assert response.json()["id"] == primary_account.id


@pytest.mark.django_db
class TestAccountUpdateDelete:
    """Update, partial update, and deletion scenarios."""

    def test_update_ok(self, admin_client, primary_account):
        url = reverse("account-detail", kwargs={"uuid": str(primary_account.uuid)})
        payload = {
            "name": "Acme Updated",
            "description": "updated",
            "contact_email": "owner@acme.com",
            "is_active": True,
        }
        response = admin_client.put(url, payload, format="json")
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Acme Updated"
        assert body["description"] == "updated"
        assert body["is_active"] is True

    def test_update_dup(self, admin_client, primary_account, secondary_account):
        url = reverse("account-detail", kwargs={"uuid": str(secondary_account.uuid)})
        payload = {
            "name": primary_account.name,
            "description": secondary_account.description or "",
            "contact_email": secondary_account.contact_email,
            "is_active": True,
        }
        response = admin_client.put(url, payload, format="json")
        assert response.status_code == 400
        assert response.json().get("code") in {"ACCOUNT_NAME_EXISTS", "INVALID_ACCOUNT_DATA"}

    def test_patch_validation(self, admin_client, primary_account):
        url = reverse("account-detail", kwargs={"uuid": str(primary_account.uuid)})
        invalid = admin_client.patch(url, {"name": 123}, format="json")
        data = invalid.json()
        assert invalid.status_code == 400
        assert data.get("code") == "INVALID_ACCOUNT_DATA"
        assert "name" in data.get("errors", {})

        valid = admin_client.patch(url, {"description": "short"}, format="json")
        assert valid.status_code == 200
        assert valid.json()["description"] == "short"

    def test_update_404(self, admin_client):
        url = reverse("account-detail", kwargs={"uuid": str(uuid.uuid4())})
        response = admin_client.put(
            url,
            {"name": "X", "description": "", "contact_email": "x@x.com", "is_active": True},
            format="json",
        )
        assert response.status_code == 404
        assert response.json().get("code") == "ACCOUNT_NOT_FOUND"

    def test_delete(self, admin_client, primary_account):
        url = reverse("account-detail", kwargs={"uuid": str(primary_account.uuid)})
        assert admin_client.delete(url).status_code == 204

        follow_up = admin_client.get(url)
        assert follow_up.status_code == 404
        if follow_up.headers.get("Content-Type", "").startswith("application/json"):
            body = follow_up.json()
            if isinstance(body, dict) and "code" in body:
                assert body["code"] == "ACCOUNT_NOT_FOUND"

    def test_delete_404(self, admin_client):
        url = reverse("account-detail", kwargs={"uuid": str(uuid.uuid4())})
        response = admin_client.delete(url)
        assert response.status_code == 404
        assert response.json().get("code") == "ACCOUNT_NOT_FOUND"
