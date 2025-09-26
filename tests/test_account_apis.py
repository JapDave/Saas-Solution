import pytest
from django.urls import reverse
from apps.accounts.models import Account


# ---------- Seed objects ----------------------------------------------------

@pytest.fixture
@pytest.mark.django_db
def acc_a(admin_user):
    return Account.objects.create(
        name="Acme",
        description="A account",
        contact_email="owner@acme.com",
        created_by=admin_user,
        updated_by=admin_user,
    )


@pytest.fixture
@pytest.mark.django_db
def acc_b(manager_user):
    return Account.objects.create(
        name="Beta Co",
        description="B account",
        contact_email="ops@beta.co",
        created_by=manager_user,
        updated_by=manager_user,
    )


@pytest.fixture
@pytest.mark.django_db
def acc_deleted(admin_user):
    acc = Account.objects.create(
        name="Zed Deleted",
        contact_email="zed@deleted.com",
        created_by=admin_user,
        updated_by=admin_user,
    )
    acc.delete()  # soft-delete (sets deleted_at)
    return acc


# ---------- CREATE ----------------------------------------------------------

@pytest.mark.django_db
def test_create_account_admin_minimal(admin_client, admin_user):
    url = reverse("accounts-list")
    payload = {"name": "Foobar", "contact_email": "admin@foobar.com"}
    r = admin_client.post(url, payload, format="json")
    assert r.status_code == 201, r.data

    body = r.json()
    assert body["name"] == "Foobar"
    assert body["contact_email"] == "admin@foobar.com"
    assert body["is_active"] is True
    assert body["deleted_at"] is None

    # If serializer returns audit fields, assert them; otherwise check DB
    if "created_by" in body:
        assert body["created_by"] == str(admin_user.pk)
        assert body["updated_by"] == str(admin_user.pk)
    obj = Account._base_manager.get(pk=body["id"])
    assert obj.created_by_id == admin_user.id
    assert obj.updated_by_id == admin_user.id


@pytest.mark.django_db
def test_create_account_validation_edges(admin_client):
    url = reverse("accounts-list")

    # missing name
    r = admin_client.post(url, {"contact_email": "x@y.com"}, format="json")
    assert r.status_code == 400

    # name too long
    r = admin_client.post(
        url, {"name": "x" * 101, "contact_email": "a@b.com"}, format="json"
    )
    assert r.status_code == 400

    # invalid email
    r = admin_client.post(
        url, {"name": "Ok", "contact_email": "not-an-email"}, format="json"
    )
    assert r.status_code == 400

    # description too long
    r = admin_client.post(
        url, {"name": "Ok", "contact_email": "ok@ok.com", "description": "y" * 501},
        format="json",
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_create_account_uniques(admin_client):
    url = reverse("accounts-list")
    r1 = admin_client.post(url, {"name": "Acme", "contact_email": "one@acme.com"}, format="json")
    assert r1.status_code == 201, r1.data

    # Duplicate name case-insensitive
    r2 = admin_client.post(url, {"name": "acme", "contact_email": "two@acme.com"}, format="json")
    assert r2.status_code == 400

    # Duplicate contact email
    r3 = admin_client.post(url, {"name": "Another", "contact_email": "one@acme.com"}, format="json")
    assert r3.status_code == 400


@pytest.mark.django_db
def test_create_authz(regular_client, unauth_client):
    url = reverse("accounts-list")
    payload = {"name": "Ok", "contact_email": "ok@ok.com"}

    assert regular_client.post(url, payload, format="json").status_code in (401, 403)
    assert unauth_client.post(url, payload, format="json").status_code == 401


# ---------- LIST ------------------------------------------------------------

@pytest.mark.django_db
def test_list_excludes_soft_deleted(admin_client, acc_a, acc_b, acc_deleted):
    url = reverse("accounts-list")
    r = admin_client.get(url)
    assert r.status_code == 200
    data = r.json()
    names = [it["name"] for it in data["results"]]
    assert "Acme" in names
    assert "Beta Co" in names
    assert "Zed Deleted" not in names


@pytest.mark.django_db
def test_list_ordering_and_paging(manager_client, acc_a, acc_b):
    url = reverse("accounts-list")

    r = manager_client.get(url + "?ordering=name")
    assert r.status_code == 200
    res = r.json()["results"]
    assert res == sorted(res, key=lambda x: x["name"].lower())

    # page_size=1 then follow next
    r1 = manager_client.get(url + "?page_size=1")
    assert r1.status_code == 200
    body1 = r1.json()
    assert body1["count"] >= 2
    assert body1["next"] is not None
    assert manager_client.get(body1["next"]).status_code == 200


@pytest.mark.django_db
def test_list_authz(regular_client, unauth_client):
    url = reverse("accounts-list")
    assert regular_client.get(url).status_code in (401, 403)
    assert unauth_client.get(url).status_code == 401


# ---------- RETRIEVE --------------------------------------------------------

@pytest.mark.django_db
def test_retrieve_ok(manager_client, acc_a):
    url = reverse("accounts-detail", args=[acc_a.pk])
    r = manager_client.get(url)
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Acme"
    assert body["deleted_at"] is None


@pytest.mark.django_db
def test_retrieve_404_soft_deleted(admin_client, acc_deleted):
    url = reverse("accounts-detail", args=[acc_deleted.pk])
    assert admin_client.get(url).status_code == 404


@pytest.mark.django_db
def test_retrieve_authz(regular_client, unauth_client, acc_a):
    url = reverse("accounts-detail", args=[acc_a.pk])
    assert regular_client.get(url).status_code in (401, 403)
    assert unauth_client.get(url).status_code == 401


# ---------- UPDATE (PUT) ----------------------------------------------------

@pytest.mark.django_db
def test_update_full_admin(admin_client, admin_user, acc_a):
    url = reverse("accounts-detail", args=[acc_a.pk])
    payload = {
        "name": "Acme Inc",
        "description": "Updated",
        "contact_email": "owner@acme.com",
        "is_active": False,
    }
    r = admin_client.put(url, payload, format="json")
    assert r.status_code == 200, r.data
    body = r.json()
    assert body["name"] == "Acme Inc"
    assert body["description"] == "Updated"
    assert body["is_active"] is False

    obj = Account._base_manager.get(pk=acc_a.pk)
    assert obj.updated_by_id == admin_user.id


@pytest.mark.django_db
def test_update_conflicts_manager(manager_client, acc_a, acc_b):
    url = reverse("accounts-detail", args=[acc_b.pk])

    # Name to existing (case-insensitive)
    r = manager_client.put(
        url,
        {"name": "Acme", "description": "x", "contact_email": "ops@beta.co", "is_active": True},
        format="json",
    )
    assert r.status_code == 400

    # Invalid email
    r2 = manager_client.put(
        url,
        {"name": "Beta Co", "description": "x", "contact_email": "not-an-email", "is_active": True},
        format="json",
    )
    assert r2.status_code == 400


@pytest.mark.django_db
def test_update_authz(regular_client, unauth_client, acc_a):
    url = reverse("accounts-detail", args=[acc_a.pk])
    assert regular_client.put(url, {"name": "x", "contact_email": "x@x.com"}, format="json").status_code in (401, 403)
    assert unauth_client.put(url, {"name": "x", "contact_email": "x@x.com"}, format="json").status_code == 401


# ---------- PARTIAL UPDATE (PATCH) -----------------------------------------

@pytest.mark.django_db
def test_patch_toggle_is_active(manager_client, acc_a):
    url = reverse("accounts-detail", args=[acc_a.pk])

    r1 = manager_client.patch(url, {"is_active": False}, format="json")
    assert r1.status_code == 200
    assert r1.json()["is_active"] is False

    r2 = manager_client.patch(url, {"is_active": True}, format="json")
    assert r2.status_code == 200
    assert r2.json()["is_active"] is True


@pytest.mark.django_db
def test_patch_validation(admin_client, acc_a):
    url = reverse("accounts-detail", args=[acc_a.pk])
    r = admin_client.patch(url, {"name": 123}, format="json")  # invalid type
    assert r.status_code == 400


@pytest.mark.django_db
def test_patch_authz(regular_client, unauth_client, acc_a):
    url = reverse("accounts-detail", args=[acc_a.pk])
    assert regular_client.patch(url, {"description": "x"}, format="json").status_code in (401, 403)
    assert unauth_client.patch(url, {"description": "x"}, format="json").status_code == 401


# ---------- DELETE (soft) ---------------------------------------------------

@pytest.mark.django_db
def test_delete_soft_and_hidden(admin_client, acc_b):
    url = reverse("accounts-detail", args=[acc_b.pk])
    assert admin_client.delete(url).status_code == 204

    # fetch returns 404
    assert admin_client.get(url).status_code == 404

    # list excludes it
    names = [a["name"] for a in admin_client.get(reverse("accounts-list")).json()["results"]]
    assert "Beta Co" not in names

    # still present in DB with deleted_at set (bypass default manager)
    raw = Account._base_manager.get(pk=acc_b.pk)
    assert raw.deleted_at is not None


@pytest.mark.django_db
def test_delete_idempotency_and_nonexistent(manager_client, acc_a):
    url = reverse("accounts-detail", args=[acc_a.pk])
    assert manager_client.delete(url).status_code == 204
    assert manager_client.delete(url).status_code == 404  # already soft-deleted

    # Nonexistent id (assuming int PK)
    assert manager_client.delete(reverse("accounts-detail", args=[999999])).status_code == 404


@pytest.mark.django_db
def test_delete_authz(regular_client, unauth_client, acc_a):
    url = reverse("accounts-detail", args=[acc_a.pk])
    assert regular_client.delete(url).status_code in (401, 403)
    assert unauth_client.delete(url).status_code == 401
