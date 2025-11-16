import uuid

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.files.models import File
from apps.knowledge_base.models import Collection, Resource
from apps.organizations.tests.factories import OrganizationFactory
from apps.users.tests.factories import UserFactory


def _create_file(organization, name="kb.pdf"):
    upload = SimpleUploadedFile(name, b"hello world", content_type="application/pdf")
    return File.objects.create(
        name=name,
        display_name=name,
        description="Test file",
        mime_type="application/pdf",
        size=upload.size,
        hash="0" * 64,
        file=upload,
        organization=organization,
        uploaded_by=None,
    )


@pytest.mark.django_db
def test_collection_bump_version_and_soft_delete():
    organization = OrganizationFactory()
    user = UserFactory()
    collection = Collection.objects.create(
        organization=organization,
        name="Internal FAQ",
        description="Helpful answers",
        created_by=user,
        updated_by=user,
    )
    assert collection.version == 1
    collection.bump_version(actor=user)
    collection.refresh_from_db()
    assert collection.version == 2
    collection.delete()
    collection.refresh_from_db()
    assert collection.state == Collection.CollectionState.DELETED
    assert collection.deleted_at is not None


@pytest.mark.django_db
def test_resource_refreshes_file_metadata():
    organization = OrganizationFactory()
    user = UserFactory()
    collection = Collection.objects.create(
        organization=organization,
        name="Docs",
        created_by=user,
        updated_by=user,
    )
    file = _create_file(organization)
    resource = Resource.objects.create(
        collection=collection,
        file_uuid=file.uuid,
        file_type="",  # should get populated
        resource_type=Resource.ResourceType.FAQ,
        created_by=user,
        updated_by=user,
    )
    assert resource.file_id == file.id
    assert resource.file_type == "pdf"
    assert resource.is_broken_reference is False


@pytest.mark.django_db
def test_resource_duplicate_file_in_collection():
    organization = OrganizationFactory()
    collection = Collection.objects.create(
        organization=organization,
        name="Policies",
        created_by=None,
        updated_by=None,
    )
    file = _create_file(organization, name="policy.pdf")
    Resource.objects.create(
        collection=collection,
        file_uuid=file.uuid,
        file_type="pdf",
        resource_type=Resource.ResourceType.GENERAL,
    )
    with pytest.raises(Exception):
        Resource.objects.create(
            collection=collection,
            file_uuid=file.uuid,
            file_type="pdf",
            resource_type=Resource.ResourceType.GENERAL,
        )
