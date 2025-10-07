import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.users.models import User, UserOrganization
from apps.users.tests.factories import UserFactory, UserOrganizationFactory
from apps.organizations.tests.factories import OrganizationFactory


@pytest.mark.django_db
class TestUserModel:
    """Behavioural tests for the custom User model."""

    def test_str_returns_email(self):
        user = UserFactory(email="member@example.com")
        assert str(user) == "member@example.com"

    def test_email_case_insensitive_unique(self):
        UserFactory(email="unique@example.com")
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                UserFactory(email="UNIQUE@example.com")

    def test_staff_email_domain_validation(self):
        user = UserFactory.build(email="admin@example.com")
        user.is_staff = True
        with pytest.raises(ValidationError):
            user.full_clean()

    def test_delete_soft_deactivates_memberships(self):
        user = UserFactory()
        membership = UserOrganizationFactory(user=user, permission_keys=["user:read"])
        user_id = user.id
        membership_id = membership.id

        user.delete()

        assert not User.objects.filter(id=user_id).exists()
        assert User.objects.with_deleted().filter(id=user_id).exists()

        archived_membership = UserOrganization.all_objects.get(id=membership_id)
        assert archived_membership.deleted_at is not None
        assert archived_membership.is_active is False

    def test_restore_reactivates_user(self):
        user = UserFactory()
        user_id = user.id
        user.delete()

        restored = User.objects.with_deleted().get(id=user_id)
        restored.restore()

        assert User.objects.filter(id=user_id).exists()
        assert restored.is_active is True


@pytest.mark.django_db
class TestUserOrganizationModel:
    """Unit tests for membership helper behaviour."""

    def test_clean_requires_active_user(self):
        user = UserFactory(is_active=False)
        organization = OrganizationFactory()
        membership = UserOrganization(
            user=user,
            organization=organization,
            assigned_by=user,
            permission_keys=[],
        )
        with pytest.raises(ValidationError):
            membership.full_clean()

    def test_add_permissions_deduplicates(self):
        membership = UserOrganizationFactory(permission_keys=["user:read"])
        membership.add_permissions(["user:update", "user:read"])
        membership.refresh_from_db()
        assert membership.permission_keys == ["user:read", "user:update"]

    def test_remove_permissions(self):
        membership = UserOrganizationFactory(permission_keys=["user:read", "user:update"])
        membership.remove_permissions(["user:read", "nonexistent:perm"])
        membership.refresh_from_db()
        assert membership.permission_keys == ["user:update"]

    def test_str_representation(self):
        membership = UserOrganizationFactory()
        assert str(membership) == f"{membership.user_id} -> {membership.organization_id}"
