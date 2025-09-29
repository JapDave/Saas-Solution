import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.accounts.tests.factories import AccountFactory
from apps.accounts.models import Account


@pytest.mark.django_db
class TestAccountModel:
    """Behavioural tests for the Account model."""

    def test_str_returns_name(self):
        account = AccountFactory(name="Acme Corp")
        assert str(account) == "Acme Corp"

    def test_name_case_insensitive_unique(self):
        AccountFactory(name="Acme", contact_email="one@acme.com")
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                AccountFactory(name="acme", contact_email="two@acme.com")

    def test_contact_email_case_insensitive_unique(self):
        AccountFactory(contact_email="owner@acme.com")
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                AccountFactory(contact_email="owner@acme.com")

    def test_full_clean_catches_invalid_email(self):
        account = AccountFactory.build(contact_email="not-an-email")
        with pytest.raises(ValidationError):
            account.full_clean()

    def test_soft_delete_hides_from_default_manager(self):
        account = AccountFactory()
        account_id = account.id
        account.delete()
        assert not Account.objects.filter(id=account_id).exists()
        assert Account._all_objects.filter(id=account_id).exists()
