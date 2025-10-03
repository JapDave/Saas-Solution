import pytest

from apps.common.validators import user_has_active_membership
from apps.organizations.tests.factories import OrganizationFactory
from apps.users.models import UserOrganization
from apps.users.tests.factories import UserFactory


@pytest.mark.django_db
def test_user_has_active_membership_true():
    user = UserFactory()
    organization = OrganizationFactory(created_by=user)
    UserOrganization.objects.create(
        user=user,
        organization=organization,
        assigned_by=user,
        is_active=True,
    )
    assert user_has_active_membership(user, organization) is True


@pytest.mark.django_db
def test_user_has_active_membership_false_when_inactive():
    user = UserFactory()
    organization = OrganizationFactory()
    UserOrganization.objects.create(
        user=user,
        organization=organization,
        assigned_by=organization.created_by,
        is_active=False,
    )
    assert user_has_active_membership(user, organization) is False


@pytest.mark.django_db
def test_user_has_active_membership_false_when_deleted():
    user = UserFactory()
    organization = OrganizationFactory()
    membership = UserOrganization.objects.create(
        user=user,
        organization=organization,
        assigned_by=organization.created_by,
    )
    membership.delete()
    assert user_has_active_membership(user, organization) is False


@pytest.mark.django_db
def test_user_has_active_membership_false_for_missing_membership():
    user = UserFactory()
    organization = OrganizationFactory()
    assert user_has_active_membership(user, organization) is False