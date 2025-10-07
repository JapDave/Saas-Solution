import pytest

from apps.accounts.tests.factories import AccountFactory
from apps.accounts.serializers import (
    AccountCreateSerializer,
    AccountUpdateSerializer,
    AccountReadSerializer,
)
from apps.common.exceptions import AccountNameExists, ContactEmailExists


@pytest.mark.django_db
class TestAccountCreateSerializer:
    def test_valid_payload_creates_account(self):
        payload = {
            "name": "Acme",
            "description": "Growth account",
            "contact_email": "acme@example.com",
        }
        serializer = AccountCreateSerializer(data=payload)
        assert serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        assert instance.name == "Acme"
        assert instance.contact_email == "acme@example.com"

    def test_duplicate_name_raises(self):
        AccountFactory(name="Acme")
        payload = {
            "name": "acme",
            "description": "Growth account",
            "contact_email": "new@example.com",
        }
        serializer = AccountCreateSerializer(data=payload)
        with pytest.raises(AccountNameExists):
            serializer.is_valid(raise_exception=True)

    def test_duplicate_contact_email_raises(self):
        AccountFactory(contact_email="support@acme.com")
        payload = {
            "name": "Acme Two",
            "description": "",
            "contact_email": "SUPPORT@ACME.COM",
        }
        serializer = AccountCreateSerializer(data=payload)
        with pytest.raises(ContactEmailExists):
            serializer.is_valid(raise_exception=True)

    def test_rejects_non_string_name(self):
        serializer = AccountCreateSerializer(data={"name": 123, "contact_email": "acme@example.com"})
        assert not serializer.is_valid()
        assert "name" in serializer.errors


@pytest.mark.django_db
class TestAccountUpdateSerializer:
    def test_update_success(self):
        account = AccountFactory(name="Original", description="")
        serializer = AccountUpdateSerializer(instance=account, data={"name": "Updated"}, partial=True)
        assert serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        assert updated.name == "Updated"

    def test_duplicate_name_on_update_raises(self):
        AccountFactory(name="Existing")
        target = AccountFactory(name="Target")
        serializer = AccountUpdateSerializer(instance=target, data={"name": "existing"}, partial=True)
        with pytest.raises(AccountNameExists):
            serializer.is_valid(raise_exception=True)

    def test_duplicate_email_on_update_raises(self):
        AccountFactory(contact_email="owner@acme.com")
        target = AccountFactory(contact_email="other@acme.com")
        serializer = AccountUpdateSerializer(instance=target, data={"contact_email": "OWNER@ACME.COM"}, partial=True)
        with pytest.raises(ContactEmailExists):
            serializer.is_valid(raise_exception=True)


@pytest.mark.django_db
def test_account_read_serializer_fields():
    account = AccountFactory()
    data = AccountReadSerializer(account).data
    expected_fields = {
        "id",
        "name",
        "description",
        "contact_email",
        "is_active",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
        "deleted_at",
    }
    assert set(data.keys()) == expected_fields

