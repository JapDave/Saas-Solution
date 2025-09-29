import factory
from factory.django import DjangoModelFactory

from apps.accounts.models import Account
from apps.users.tests.factories import UserFactory


class AccountFactory(DjangoModelFactory):
    """Factory for the Account model."""

    class Meta:
        model = Account

    name = factory.Sequence(lambda n: f"Account {n}")
    description = factory.Faker("sentence", nb_words=6)
    contact_email = factory.Sequence(lambda n: f"account{n}@example.com")
    created_by = factory.SubFactory(UserFactory)
    updated_by = factory.LazyAttribute(lambda obj: obj.created_by)
