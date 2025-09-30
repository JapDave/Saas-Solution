import pytest
from rest_framework.test import APIRequestFactory

from apps.common.exceptions import InvalidUserData, UserAlreadyMember, UserNotMember
from apps.organizations.tests.factories import OrganizationFactory
from apps.users.models import UserOrganization
from apps.users.serializers import (
    MembershipMutationSerializer,
    MembershipRemovalSerializer,
    UserCreateSerializer,
)
from apps.users.tests.factories import SuperUserFactory, UserFactory, UserOrganizationFactory


@pytest.fixture
@pytest.mark.django_db
def superadmin_request():
    factory = APIRequestFactory()
    request = factory.post("/api/users/")
    request.user = SuperUserFactory(email="superadmin@hudhud.ai")
    return request


@pytest.mark.django_db
class TestUserCreateSerializer:
    def test_valid_payload_creates_user_and_membership(self, superadmin_request):
        organization = OrganizationFactory()
        payload = {
            "email": "new.user@example.com",
            "password": "SecurePass8",
            "full_name": "New User",
            "memberships": [
                {"organization": organization.pk, "permissions": ["users:read"]},
            ],
        }
        serializer = UserCreateSerializer(data=payload, context={"request": superadmin_request})
        assert serializer.is_valid(raise_exception=True)
        user = serializer.save()
        membership = user.memberships.get()
        assert membership.organization == organization
        assert membership.permission_keys == ["users:read"]

    def test_duplicate_membership_entries_raise(self, superadmin_request):
        organization = OrganizationFactory()
        payload = {
            "email": "dup.user@example.com",
            "password": "SecurePass8",
            "full_name": "Dup User",
            "memberships": [
                {"organization": organization.pk},
                {"organization": organization.pk},
            ],
        }
        serializer = UserCreateSerializer(data=payload, context={"request": superadmin_request})
        with pytest.raises(InvalidUserData):
            serializer.is_valid(raise_exception=True)

    def test_missing_memberships_raise(self, superadmin_request):
        payload = {
            "email": "no.membership@example.com",
            "password": "SecurePass8",
            "full_name": "No Membership",
            "memberships": [],
        }
        serializer = UserCreateSerializer(data=payload, context={"request": superadmin_request})
        with pytest.raises(InvalidUserData):
            serializer.is_valid(raise_exception=True)


@pytest.mark.django_db
class TestMembershipMutationSerializer:
    def test_create_membership(self, superadmin_request):
        organization = OrganizationFactory()
        user = UserFactory()
        serializer = MembershipMutationSerializer(
            data={"organization": organization.pk, "permissions": ["users:read"]},
            context={"request": superadmin_request, "user": user},
        )
        assert serializer.is_valid(raise_exception=True)
        membership = serializer.save()
        assert membership.organization == organization
        assert membership.permission_keys == ["users:read"]

    def test_duplicate_membership_raises(self, superadmin_request):
        membership = UserOrganizationFactory(permission_keys=["users:read"])
        serializer = MembershipMutationSerializer(
            data={"organization": membership.organization.pk},
            context={"request": superadmin_request, "user": membership.user},
        )
        with pytest.raises(UserAlreadyMember):
            serializer.is_valid(raise_exception=True)


@pytest.mark.django_db
class TestMembershipRemovalSerializer:
    def test_remove_membership(self, superadmin_request):
        membership = UserOrganizationFactory(permission_keys=["users:read"])
        serializer = MembershipRemovalSerializer(
            data={"organization": membership.organization.pk},
            context={"request": superadmin_request, "user": membership.user},
        )
        assert serializer.is_valid(raise_exception=True)
        serializer.remove()
        assert not UserOrganization.objects.filter(id=membership.id).exists()

    def test_remove_missing_membership_raises(self, superadmin_request):
        organization = OrganizationFactory()
        user = UserFactory()
        serializer = MembershipRemovalSerializer(
            data={"organization": organization.pk},
            context={"request": superadmin_request, "user": user},
        )
        assert serializer.is_valid(raise_exception=True)
        with pytest.raises(UserNotMember):
            serializer.remove()
