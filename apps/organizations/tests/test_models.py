import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.organizations.tests.factories import OrganizationFactory
from apps.organizations.models import Organization


@pytest.mark.django_db
class TestOrganizationModel:
    def test_str_includes_name(self):
        organization = OrganizationFactory(name="Alpha", account__name="Acme")
        assert "Alpha" in str(organization)

    def test_name_unique_within_account_case_insensitive(self):
        org = OrganizationFactory(name="North")
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                OrganizationFactory(account=org.account, name="north")

    def test_same_name_allowed_across_accounts(self):
        OrganizationFactory(name="Shared")
        other = OrganizationFactory(name="Shared", account__name="Different")
        assert other.name == "Shared"

    def test_full_clean_validates_max_length(self):
        organization = OrganizationFactory.build(name="a" * 101)
        with pytest.raises(ValidationError):
            organization.full_clean()

    def test_soft_delete_hides_from_default_manager(self):
        organization = OrganizationFactory()
        org_id = organization.id
        organization.delete()
        assert not Organization.objects.filter(id=org_id).exists()
        assert Organization._all_objects.filter(id=org_id).exists()
