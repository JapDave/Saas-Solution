import factory
from factory import LazyAttribute
from factory.django import DjangoModelFactory
from django.contrib.auth import get_user_model

from apps.users.models import UserOrganization

User = get_user_model()


class UserFactory(DjangoModelFactory):
    """Factory for the custom User model."""

    class Meta:
        model = User
        django_get_or_create = ("email",)

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    full_name = factory.Faker("name")
    password = factory.PostGenerationMethodCall("set_password", "pass1234")
    is_active = True
    is_staff = False
    is_superuser = False


class StaffUserFactory(UserFactory):
    is_staff = True


class SuperUserFactory(UserFactory):
    is_staff = True
    is_superuser = True


class UserOrganizationFactory(DjangoModelFactory):
    class Meta:
        model = UserOrganization

    user = factory.SubFactory(UserFactory)
    organization = factory.SubFactory("apps.organizations.tests.factories.OrganizationFactory")
    assigned_by = LazyAttribute(lambda obj: obj.user)
    permission_keys = factory.List([])
