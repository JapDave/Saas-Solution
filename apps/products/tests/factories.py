import factory
from factory.django import DjangoModelFactory

from .models import Product, Module


class ProductFactory(DjangoModelFactory):
    """Factory for the Product model."""

    class Meta:
        model = Product

    key = factory.Sequence(lambda n: f"PRODUCT_KEY_{n}")
    name = factory.Faker("company")
    description = factory.Faker("paragraph", nb_sentences=3)
    available_module_keys = factory.LazyFunction(list)
    target_segments = factory.LazyFunction(list)
    use_cases = factory.LazyFunction(list)
    is_active = True


class ModuleFactory(DjangoModelFactory):
    """Factory for the Module model."""

    class Meta:
        model = Module

    key = factory.Sequence(lambda n: f"MODULE_KEY_{n}")
    # Generates unique 4-letter uppercase codes like 'AAAA', 'AAAB', etc.
    code = factory.Sequence(
        lambda n: "".join(
            [chr(65 + (n // (26**i)) % 26) for i in range(3, -1, -1)]
        )
    )
    name = factory.Faker("bs")
    description = factory.Faker("paragraph", nb_sentences=2)
    subscribable = True
    configurable_attributes = factory.LazyFunction(dict)
    exposed_permissions = factory.LazyFunction(list)
    is_active = True
