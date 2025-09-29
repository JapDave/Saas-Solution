import pytest

from apps.accounts.tests.factories import AccountFactory
from apps.organizations.tests.factories import OrganizationFactory
from apps.organizations.serializers import (
    OrganizationCreateSerializer,
    OrganizationUpdateSerializer,
    OrganizationReadSerializer,
)
from apps.common.exceptions import OrganizationNameExists, InvalidLogoUrl


@pytest.mark.django_db
class TestOrganizationCreateSerializer:
    def test_valid_payload_creates_organization(self):
        account = AccountFactory()
        payload = {
            "account": account.pk,
            "name": "HQ",
            "description": "Main office",
            "logo_url": "https://example.com/logo.png",
        }
        serializer = OrganizationCreateSerializer(data=payload)
        assert serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        assert instance.account == account
        assert instance.name == "HQ"

    def test_duplicate_name_within_account_raises(self):
        organization = OrganizationFactory(name="North")
        payload = {
            "account": organization.account.pk,
            "name": "north",
            "description": "",
        }
        serializer = OrganizationCreateSerializer(data=payload)
        with pytest.raises(OrganizationNameExists):
            serializer.is_valid(raise_exception=True)

    def test_invalid_logo_url_raises(self):
        account = AccountFactory()
        payload = {
            "account": account.pk,
            "name": "HQ",
            "logo_url": "ftp://invalid.example.com",
        }
        serializer = OrganizationCreateSerializer(data=payload)
        with pytest.raises(InvalidLogoUrl):
            serializer.is_valid(raise_exception=True)


@pytest.mark.django_db
class TestOrganizationUpdateSerializer:
    def test_update_success(self):
        organization = OrganizationFactory(name="Alpha", description="")
        serializer = OrganizationUpdateSerializer(
            instance=organization,
            data={"description": "Updated", "is_active": False},
            partial=True,
        )
        assert serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        assert updated.description == "Updated"
        assert updated.is_active is False

    def test_duplicate_name_on_update_raises(self):
        existing = OrganizationFactory(name="Existing")
        target = OrganizationFactory(account=existing.account, name="Target")
        serializer = OrganizationUpdateSerializer(
            instance=target,
            data={"name": "existing"},
            partial=True,
        )
        with pytest.raises(OrganizationNameExists):
            serializer.is_valid(raise_exception=True)

    def test_invalid_logo_url_on_update_raises(self):
        target = OrganizationFactory()
        serializer = OrganizationUpdateSerializer(
            instance=target,
            data={"logo_url": "ftp://bad.example.com"},
            partial=True,
        )
        with pytest.raises(InvalidLogoUrl):
            serializer.is_valid(raise_exception=True)


@pytest.mark.django_db
def test_organization_read_serializer_fields():
    organization = OrganizationFactory()
    data = OrganizationReadSerializer(organization).data
    expected_fields = {
        "id",
        "account",
        "name",
        "description",
        "logo_url",
        "is_active",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
        "deleted_at",
    }
    assert set(data.keys()) == expected_fields


