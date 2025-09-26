import uuid
import pytest
from django.urls import reverse


# ---------------- Permissions & Scoping ----------------

@pytest.mark.django_db
def test_staff_scope_crud(manager_client_assigned_acc_a, org_a, org_c_in_b, acc_a, acc_b):
    # list shows only assigned (acc_a) orgs
    url = reverse("organizations-list")
    r = manager_client_assigned_acc_a.get(url)
    assert r.status_code == 200
    ids = {o["id"] for o in r.json()["results"]}
    assert org_a.id in ids
    assert org_c_in_b.id not in ids  # from acc_b, not assigned

    # create allowed for assigned account
    r = manager_client_assigned_acc_a.post(url, {"account": acc_a.id, "name": "HQ"}, format="json")
    assert r.status_code == 201

    # create forbidden for unassigned account
    r = manager_client_assigned_acc_a.post(url, {"account": acc_b.id, "name": "OtherHQ"}, format="json")
    assert r.status_code == 403 and r.json().get("code") == "INSUFFICIENT_PERMISSIONS"

    # update allowed for assigned org
    u = reverse("organizations-detail", kwargs={"uuid": str(org_a.uuid)})
    r = manager_client_assigned_acc_a.patch(u, {"description": "scoped"}, format="json")
    assert r.status_code == 200 and r.json()["description"] == "scoped"

    # update on unassigned org -> 404 (scoped queryset)
    u2 = reverse("organizations-detail", kwargs={"uuid": str(org_c_in_b.uuid)})
    r = manager_client_assigned_acc_a.patch(u2, {"description": "nope"}, format="json")
    assert r.status_code == 404 and r.json().get("code") == "ORGANIZATION_NOT_FOUND"

    # delete assigned ok
    r = manager_client_assigned_acc_a.delete(u)
    assert r.status_code == 204

    # delete unassigned -> 404
    r = manager_client_assigned_acc_a.delete(u2)
    assert r.status_code == 404 and r.json().get("code") == "ORGANIZATION_NOT_FOUND"


@pytest.mark.django_db
def test_staff_no_assignments(manager_client_with_no_assignments, acc_a):
    url = reverse("organizations-list")
    r = manager_client_with_no_assignments.get(url)
    assert r.status_code == 200 and r.json()["results"] == []

    r = manager_client_with_no_assignments.post(url, {"account": acc_a.id, "name": "Nope"}, format="json")
    assert r.status_code == 403 and r.json().get("code") == "INSUFFICIENT_PERMISSIONS"


@pytest.mark.django_db
def test_user_owner_update(regular_client, org_owned_by_user, acc_a):
    # user cannot list/create
    url = reverse("organizations-list")
    r = regular_client.get(url)
    assert r.status_code == 403 and r.json().get("code") == "INSUFFICIENT_PERMISSIONS"
    r = regular_client.post(url, {"account": acc_a.id, "name": "UHQ"}, format="json")
    assert r.status_code == 403 and r.json().get("code") == "INSUFFICIENT_PERMISSIONS"

    # can patch own org
    u = reverse("organizations-detail", kwargs={"uuid": str(org_owned_by_user.uuid)})
    r = regular_client.patch(u, {"description": "mine"}, format="json")
    assert r.status_code == 200 and r.json()["description"] == "mine"


# ---------------- Create ----------------

@pytest.mark.django_db
def test_admin_create_min(admin_client, acc_a):
    url = reverse("organizations-list")
    r = admin_client.post(url, {"account": acc_a.id, "name": "HQ"}, format="json")
    assert r.status_code == 201
    b = r.json()
    assert b["account"] == acc_a.id and b["name"] == "HQ"
    assert b["is_active"] is True
    assert "deleted_at" in b and b["deleted_at"] is None


@pytest.mark.django_db
def test_create_validation(admin_client, acc_a):
    url = reverse("organizations-list")

    # missing account
    r = admin_client.post(url, {"name": "HQ"}, format="json")
    assert r.status_code == 400 and r.json().get("code") == "INVALID_ORGANIZATION_DATA"

    # missing name
    r = admin_client.post(url, {"account": acc_a.id}, format="json")
    assert r.status_code == 400 and r.json().get("code") == "INVALID_ORGANIZATION_DATA"

    # wrong type for name
    r = admin_client.post(url, {"account": acc_a.id, "name": 123}, format="json")
    data = r.json()
    assert r.status_code == 400 and data.get("code") == "INVALID_ORGANIZATION_DATA"
    assert "name" in data.get("errors", {})



@pytest.mark.django_db
def test_create_uniques_per_account(admin_client, acc_a, acc_b):
    url = reverse("organizations-list")

    assert admin_client.post(url, {"account": acc_a.id, "name": "North"}, format="json").status_code == 201

    # duplicate in same account (case-insensitive)
    r = admin_client.post(url, {"account": acc_a.id, "name": "north"}, format="json")
    assert r.status_code == 400 and r.json().get("code") in {"ORGANIZATION_NAME_EXISTS", "INVALID_ORGANIZATION_DATA"}

    # same name in different account ok
    r = admin_client.post(url, {"account": acc_b.id, "name": "north"}, format="json")
    assert r.status_code == 201


# ---------------- List / Retrieve ----------------

@pytest.mark.django_db
def test_list_and_filters(admin_client, org_a, org_b, org_c_in_b):
    url = reverse("organizations-list")
    r = admin_client.get(url)
    assert r.status_code == 200
    ids = {o["id"] for o in r.json()["results"]}
    assert org_a.id in ids and org_b.id in ids and org_c_in_b.id in ids

    # ordering & filters smoke
    assert admin_client.get(url + "?ordering=name").status_code == 200
    assert admin_client.get(url + "?is_active=true").status_code == 200
    assert admin_client.get(url + f"?account={org_a.account_id}").status_code == 200


@pytest.mark.django_db
def test_get(admin_client, org_a):
    url = reverse("organizations-detail", kwargs={"uuid": str(org_a.uuid)})
    r = admin_client.get(url)
    assert r.status_code == 200 and r.json()["id"] == org_a.id


# ---------------- Update / Patch / Delete ----------------

@pytest.mark.django_db
def test_update_ok(admin_client, org_a):
    url = reverse("organizations-detail", kwargs={"uuid": str(org_a.uuid)})
    payload = {
        "account": org_a.account_id,
        "name": "Alpha HQ",
        "description": "Main office",
        "logo_url": "",
        "is_active": True,
    }
    r = admin_client.put(url, payload, format="json")
    assert r.status_code == 200
    b = r.json()
    assert b["name"] == "Alpha HQ" and b["description"] == "Main office" and b["is_active"] is True


@pytest.mark.django_db
def test_update_dup(admin_client, org_a, org_b):
    # rename org_b to org_a's name in same account -> 400 with code
    url = reverse("organizations-detail", kwargs={"uuid": str(org_b.uuid)})
    payload = {
        "account": org_b.account_id,
        "name": org_a.name,
        "description": "",
        "logo_url": "",
        "is_active": True,
    }
    r = admin_client.put(url, payload, format="json")
    assert r.status_code == 400 and r.json().get("code") in {"ORGANIZATION_NAME_EXISTS", "INVALID_ORGANIZATION_DATA"}


@pytest.mark.django_db
def test_patch_validation(admin_client, org_a):
    url = reverse("organizations-detail", kwargs={"uuid": str(org_a.uuid)})

    r = admin_client.patch(url, {"name": 123}, format="json")
    data = r.json()
    assert r.status_code == 400 and data.get("code") == "INVALID_ORGANIZATION_DATA" and "name" in data.get("errors", {})

    r = admin_client.patch(url, {"description": "short"}, format="json")
    assert r.status_code == 200 and r.json()["description"] == "short"


@pytest.mark.django_db
def test_update_404(admin_client, acc_a):
    url = reverse("organizations-detail", kwargs={"uuid": str(uuid.uuid4())})
    payload = {"account": acc_a.id, "name": "X", "description": "", "logo_url": "", "is_active": True}
    r = admin_client.put(url, payload, format="json")
    assert r.status_code == 404 and r.json().get("code") == "ORGANIZATION_NOT_FOUND"


@pytest.mark.django_db
def test_delete(admin_client, org_a):
    url = reverse("organizations-detail", kwargs={"uuid": str(org_a.uuid)})
    assert admin_client.delete(url).status_code == 204

    r2 = admin_client.get(url)
    assert r2.status_code == 404 and r2.json().get("code") == "ORGANIZATION_NOT_FOUND"


@pytest.mark.django_db
def test_delete_404(admin_client):
    url = reverse("organizations-detail", kwargs={"uuid": str(uuid.uuid4())})
    r = admin_client.delete(url)
    assert r.status_code == 404 and r.json().get("code") == "ORGANIZATION_NOT_FOUND"
