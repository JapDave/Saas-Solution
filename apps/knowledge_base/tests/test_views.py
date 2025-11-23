import uuid

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.files.models import File
from apps.knowledge_base.tests.factories import CollectionFactory
from apps.organizations.tests.factories import OrganizationFactory
from apps.products.models import Module
from apps.roles.constants import KNOWLEDGE_BASE_PERMISSION_KEYS
from apps.subscriptions.models import Subscription
from apps.users.models import UserOrganization
from apps.users.tests.factories import UserFactory


def _create_file(organization, user, name="demo.pdf"):
    upload = SimpleUploadedFile(name, b"hello world", content_type="application/pdf")
    return File.objects.create(
        name=name,
        display_name=name,
        description="",
        mime_type="application/pdf",
        size=upload.size,
        hash="0" * 64,
        file=upload,
        organization=organization,
        uploaded_by=user,
    )


@pytest.fixture
def kb_client(db):
    organization = OrganizationFactory()
    user = UserFactory()
    UserOrganization.objects.create(
        user=user,
        organization=organization,
        permission_keys=list(KNOWLEDGE_BASE_PERMISSION_KEYS),
        assigned_by=user,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    module, _ = Module.objects.get_or_create(
        key="KNOWLEDGE_BASE_MANAGEMENT",
        defaults={
            "code": "KB",
            "name": "Knowledge Base",
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
            "configuration": {
                "kb.collections.max": 5,
                "kb.resources_per_collection": 1,
            },
        },
    )
    return organization, user, client


@pytest.mark.django_db
def test_create_collection(kb_client):
    organization, _, client = kb_client
    url = reverse("kb-collections-list", kwargs={"organization_uuid": organization.uuid})
    response = client.post(
        url,
        {"name": "Customer FAQ", "description": "Frequently asked questions."},
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["name"] == "Customer FAQ"
    assert body["version"] == 1


@pytest.mark.django_db
def test_add_resource_to_collection(kb_client):
    organization, user, client = kb_client
    file = _create_file(organization, user)
    collection_url = reverse("kb-collections-list", kwargs={"organization_uuid": organization.uuid})
    collection = client.post(collection_url, {"name": "Policies"}, format="json").json()
    resources_url = reverse(
        "kb-resources-list",
        kwargs={"organization_uuid": organization.uuid, "collection_uuid": collection["uuid"]},
    )
    response = client.post(
        resources_url,
        {"file_id": str(file.uuid), "resource_type": "faq", "title": "Policy PDF"},
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["file_type"] == "pdf"
    detail = client.get(
        reverse("kb-collections-detail", kwargs={"organization_uuid": organization.uuid, "uuid": collection["uuid"]})
    )
    assert detail.json()["version"] == 2


@pytest.mark.django_db
def test_resource_limit_enforced(kb_client):
    organization, user, client = kb_client
    file_one = _create_file(organization, user, name="doc1.pdf")
    file_two = _create_file(organization, user, name="doc2.pdf")
    collection = client.post(
        reverse("kb-collections-list", kwargs={"organization_uuid": organization.uuid}),
        {"name": "Limits"},
        format="json",
    ).json()
    resources_url = reverse(
        "kb-resources-list",
        kwargs={"organization_uuid": organization.uuid, "collection_uuid": collection["uuid"]},
    )
    assert (
        client.post(
            resources_url,
            {"file_id": str(file_one.uuid), "resource_type": "general"},
            format="json",
        ).status_code
        == status.HTTP_201_CREATED
    )
    response = client.post(
        resources_url,
        {"file_id": str(file_two.uuid), "resource_type": "general"},
        format="json",
    )
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["code"] == "KB_LIMIT_EXCEEDED"


@pytest.mark.django_db
def test_move_resource_between_collections(kb_client):
    organization, user, client = kb_client
    file = _create_file(organization, user, name="move.pdf")
    source = client.post(
        reverse("kb-collections-list", kwargs={"organization_uuid": organization.uuid}),
        {"name": "Source"},
        format="json",
    ).json()
    destination = client.post(
        reverse("kb-collections-list", kwargs={"organization_uuid": organization.uuid}),
        {"name": "Destination"},
        format="json",
    ).json()
    resource = client.post(
        reverse("kb-resources-list", kwargs={"organization_uuid": organization.uuid, "collection_uuid": source["uuid"]}),
        {"file_id": str(file.uuid), "resource_type": "general"},
        format="json",
    ).json()
    move_url = reverse(
        "kb-resources-move",
        kwargs={"organization_uuid": organization.uuid, "collection_uuid": source["uuid"], "uuid": resource["uuid"]},
    )
    response = client.post(move_url, {"destination_collection_uuid": destination["uuid"]}, format="json")
    assert response.status_code == status.HTTP_200_OK
    list_dest = client.get(
        reverse("kb-resources-list", kwargs={"organization_uuid": organization.uuid, "collection_uuid": destination["uuid"]})
    )
    results = list_dest.json()["results"]
    assert any(item["uuid"] == resource["uuid"] for item in results)
