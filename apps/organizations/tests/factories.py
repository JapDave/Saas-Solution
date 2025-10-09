import factory
from factory.django import DjangoModelFactory

from apps.organizations.models import Organization
from apps.accounts.tests.factories import AccountFactory


class OrganizationFactory(DjangoModelFactory):
    """Factory for the Organization model."""

    class Meta:
        model = Organization

    account = factory.SubFactory(AccountFactory)
    name = factory.Sequence(lambda n: f"Organization {n}")
    description = factory.Faker("sentence", nb_words=8)
    logo_url = factory.LazyFunction(lambda: "")

    @factory.lazy_attribute
    def created_by(self):
        return getattr(self.account, "created_by", None)

    @factory.lazy_attribute
    def updated_by(self):
        return self.created_by
