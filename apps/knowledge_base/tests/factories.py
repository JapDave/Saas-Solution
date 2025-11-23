import factory

from apps.knowledge_base.models import Collection
from apps.organizations.tests.factories import OrganizationFactory
from apps.users.tests.factories import UserFactory


class CollectionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Collection

    organization = factory.SubFactory(OrganizationFactory)
    name = factory.Sequence(lambda n: f"Collection {n}")
    description = "Sample knowledge collection"
    created_by = factory.SubFactory(UserFactory)
    updated_by = factory.SelfAttribute("created_by")

