import uuid
import pytest
from django.urls import reverse


# ---------------- Permissions ----------------

@pytest.mark.django_db
def test_staff_view(manager_client, acc_a, acc_b):
    url = reverse("accounts-list")
    r = manager_client.get(url)
    assert r.status_code == 200

    url = reverse("accounts-detail", kwargs={"uuid": str(acc_a.uuid)})
    r = manager_client.get(url)
    assert r.status_code == 200

    url = reverse("accounts-list")
    r = manager_client.post(url, {"name": "X", "contact_email": "x@x.com"}, format="json")
    assert r.status_code == 403 and r.json().get("code") == "INSUFFICIENT_PERMISSIONS"

    url = reverse("accounts-detail", kwargs={"uuid": str(acc_a.uuid)})
    r = manager_client.put(url, {"name": "N", "description": "", "contact_email": "n@n.com", "is_active": True}, format="json")
    assert r.status_code == 403 and r.json().get("code") == "INSUFFICIENT_PERMISSIONS"
    r = manager_client.patch(url, {"description": "nope"}, format="json")
    assert r.status_code == 403 and r.json().get("code") == "INSUFFICIENT_PERMISSIONS"
    r = manager_client.delete(url)
    assert r.status_code == 403 and r.json().get("code") == "INSUFFICIENT_PERMISSIONS"


@pytest.mark.django_db
def test_user_owner_update(regular_client, acc_owned_by_user):
    url = reverse("accounts-list")
    r = regular_client.get(url)
    assert r.status_code == 403 and r.json().get("code") == "INSUFFICIENT_PERMISSIONS"
    r = regular_client.post(url, {"name": "Own", "contact_email": "own@me.com"}, format="json")
    assert r.status_code == 403 and r.json().get("code") == "INSUFFICIENT_PERMISSIONS"

    url = reverse("accounts-detail", kwargs={"uuid": str(acc_owned_by_user.uuid)})
    r = regular_client.patch(url, {"description": "mine"}, format="json")
    assert r.status_code == 200 and r.json()["description"] == "mine"


# ---------------- Create ----------------

@pytest.mark.django_db
def test_admin_create(admin_client):
    url = reverse("accounts-list")
    r = admin_client.post(url, {"name": "Foobar", "contact_email": "admin@foobar.com"}, format="json")
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Foobar"
    assert body["contact_email"] == "admin@foobar.com"
    assert body["is_active"] is True
    assert "deleted_at" in body and body["deleted_at"] is None


@pytest.mark.django_db
def test_create_validation(admin_client):
    url = reverse("accounts-list")

    r = admin_client.post(url, {"contact_email": "x@y.com"}, format="json")
    assert r.status_code == 400 and r.json().get("code") == "INVALID_ACCOUNT_DATA"

    r = admin_client.post(url, {"name": "X"}, format="json")
    assert r.status_code == 400 and r.json().get("code") == "INVALID_ACCOUNT_DATA"

    r = admin_client.post(url, {"name": 123, "contact_email": "x@y.com"}, format="json")
    data = r.json()
    assert r.status_code == 400 and data.get("code") == "INVALID_ACCOUNT_DATA" and "name" in data.get("errors", {})


@pytest.mark.django_db
def test_create_uniques(admin_client):
    url = reverse("accounts-list")
    assert admin_client.post(url, {"name": "Acme", "contact_email": "one@acme.com"}, format="json").status_code == 201

    r = admin_client.post(url, {"name": "acme", "contact_email": "two@acme.com"}, format="json")
    assert r.status_code == 400 and r.json().get("code") in {"ACCOUNT_NAME_EXISTS", "INVALID_ACCOUNT_DATA"}

    r = admin_client.post(url, {"name": "NewCo", "contact_email": "ONE@ACME.COM"}, format="json")
    assert r.status_code == 400 and r.json().get("code") in {"CONTACT_EMAIL_EXISTS", "INVALID_ACCOUNT_DATA"}


# ---------------- List / Retrieve ----------------

@pytest.mark.django_db
def test_list(admin_client, acc_a, acc_b):
    url = reverse("accounts-list")
    r = admin_client.get(url)
    assert r.status_code == 200
    ids = {o["id"] for o in r.json()["results"]}
    assert acc_a.id in ids and acc_b.id in ids

    assert admin_client.get(url + "?ordering=name").status_code == 200
    assert admin_client.get(url + "?is_active=true").status_code == 200


@pytest.mark.django_db
def test_get(admin_client, acc_a):
    url = reverse("accounts-detail", kwargs={"uuid": str(acc_a.uuid)})
    r = admin_client.get(url)
    assert r.status_code == 200 and r.json()["id"] == acc_a.id


# ---------------- Update / Patch / Delete ----------------

@pytest.mark.django_db
def test_update_ok(admin_client, acc_a):
    url = reverse("accounts-detail", kwargs={"uuid": str(acc_a.uuid)})
    payload = {"name": "Acme Updated", "description": "updated", "contact_email": "owner@acme.com", "is_active": True}
    r = admin_client.put(url, payload, format="json")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Acme Updated" and body["description"] == "updated" and body["is_active"] is True


@pytest.mark.django_db
def test_update_dup(admin_client, acc_a, acc_b):
    url = reverse("accounts-detail", kwargs={"uuid": str(acc_b.uuid)})
    payload = {"name": acc_a.name, "description": acc_b.description or "", "contact_email": acc_b.contact_email, "is_active": True}
    r = admin_client.put(url, payload, format="json")
    assert r.status_code == 400 and r.json().get("code") in {"ACCOUNT_NAME_EXISTS", "INVALID_ACCOUNT_DATA"}


@pytest.mark.django_db
def test_patch_validation(admin_client, acc_a):
    url = reverse("accounts-detail", kwargs={"uuid": str(acc_a.uuid)})
    r = admin_client.patch(url, {"name": 123}, format="json")
    data = r.json()
    assert r.status_code == 400 and data.get("code") == "INVALID_ACCOUNT_DATA" and "name" in data.get("errors", {})
    r = admin_client.patch(url, {"description": "short"}, format="json")
    assert r.status_code == 200 and r.json()["description"] == "short"


@pytest.mark.django_db
def test_update_404(admin_client):
    url = reverse("accounts-detail", kwargs={"uuid": str(uuid.uuid4())})
    r = admin_client.put(url, {"name": "X", "description": "", "contact_email": "x@x.com", "is_active": True}, format="json")
    assert r.status_code == 404 and r.json().get("code") == "ACCOUNT_NOT_FOUND"


@pytest.mark.django_db
def test_delete(admin_client, acc_a):
    url = reverse("accounts-detail", kwargs={"uuid": str(acc_a.uuid)})
    assert admin_client.delete(url).status_code == 204
    r2 = admin_client.get(url)
    assert r2.status_code == 404
    if r2.headers.get("Content-Type", "").startswith("application/json"):
        data = r2.json()
        if isinstance(data, dict) and "code" in data:
            assert data["code"] == "ACCOUNT_NOT_FOUND"


@pytest.mark.django_db
def test_delete_404(admin_client):
    url = reverse("accounts-detail", kwargs={"uuid": str(uuid.uuid4())})
    r = admin_client.delete(url)
    assert r.status_code == 404 and r.json().get("code") == "ACCOUNT_NOT_FOUND"
