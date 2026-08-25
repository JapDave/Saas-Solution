import pytest
from rest_framework import serializers
from rest_framework.test import APIRequestFactory

from apps.common.exceptions import (
    CustomValidationError,
    CustomError,
    INVALID_USER_DATA,
    USER_ALREADY_MEMBER,
    USER_NOT_MEMBER,
)
from apps.organizations.tests.factories import OrganizationFactory
from apps.roles.constants import ROLE_ORGANIZATION_OWNER
from apps.roles.models import Role, RoleAssignment
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
    request.user = SuperUserFactory(email="superadmin@saas-platform.ai")
    return request


@pytest.mark.django_db
class TestUserCreateSerializer:
    def test_valid_payload_creates_user_and_membership(self, superadmin_request):
        organization = OrganizationFactory()
        role = Role.objects.create(
            organization=organization,
            name="Org Admin",
            description="Org administrator",
            permissions=["user:read"],
            role_type=Role.RoleType.USER_CUSTOM,
            is_active=True,
            created_by=organization.created_by,
        )
        payload = {
            "email": "new.user@example.com",
            "password": "SecurePass8",
            "full_name": "New User",
            "memberships": [
                {
                    "organization": organization.pk,
                    "permissions": ["user:read"],
                    "roles": [str(role.uuid)],
                },
            ],
        }
        serializer = UserCreateSerializer(data=payload, context={"request": superadmin_request})
        assert serializer.is_valid(raise_exception=True)
        user = serializer.save()
        membership = user.memberships.get()
        assert membership.organization == organization
        assert membership.permission_keys == ["user:read"]
        assert RoleAssignment.objects.filter(
            organization=organization,
            user=user,
            role=role,
            deleted_at__isnull=True,
        ).exists()

    def test_full_name_optional(self, superadmin_request):
        organization = OrganizationFactory()
        role = Role.objects.create(
            organization=organization,
            name="Org Admin",
            description="Org administrator",
            permissions=["user:read"],
            role_type=Role.RoleType.USER_CUSTOM,
            is_active=True,
            created_by=organization.created_by,
        )
        payload = {
            "email": "optional.name@example.com",
            "password": "SecurePass8",
            "memberships": [
                {
                    "organization": organization.pk,
                    "roles": [str(role.uuid)],
                },
            ],
        }
        serializer = UserCreateSerializer(data=payload, context={"request": superadmin_request})
        assert serializer.is_valid(raise_exception=True)
        user = serializer.save()
        assert user.full_name == ""

    def test_duplicate_membership_entries_raise(self, superadmin_request):
        organization = OrganizationFactory()
        role = Role.objects.create(
            organization=organization,
            name="Org Admin",
            description="Org administrator",
            permissions=["user:read"],
            role_type=Role.RoleType.USER_CUSTOM,
            is_active=True,
            created_by=organization.created_by,
        )
        payload = {
            "email": "dup.user@example.com",
            "password": "SecurePass8",
            "full_name": "Dup User",
            "memberships": [
                {"organization": organization.pk, "roles": [str(role.uuid)]},
                {"organization": organization.pk, "roles": [str(role.uuid)]},
            ],
        }
        serializer = UserCreateSerializer(data=payload, context={"request": superadmin_request})
        with pytest.raises(CustomValidationError) as exc:
            serializer.is_valid(raise_exception=True)

    def test_missing_memberships_raise(self, superadmin_request):
        payload = {
            "email": "no.membership@example.com",
            "password": "SecurePass8",
            "full_name": "No Membership",
            "memberships": [],
        }
        serializer = UserCreateSerializer(data=payload, context={"request": superadmin_request})
        with pytest.raises(CustomValidationError) as exc:
            serializer.is_valid(raise_exception=True)


@pytest.mark.django_db
class TestMembershipMutationSerializer:
    def test_create_membership(self, superadmin_request):
        organization = OrganizationFactory()
        role = Role.objects.create(
            organization=organization,
            name="Org Admin",
            description="Org administrator",
            permissions=["user:read"],
            role_type=Role.RoleType.USER_CUSTOM,
            is_active=True,
            created_by=organization.created_by,
        )
        user = UserFactory()
        serializer = MembershipMutationSerializer(
            data={
                "organization": organization.pk,
                "permissions": ["user:read"],
                "roles": [str(role.uuid)],
            },
            context={"request": superadmin_request, "user": user},
        )
        assert serializer.is_valid(raise_exception=True)
        membership = serializer.save()
        assert membership.organization == organization
        assert membership.permission_keys == ["user:read"]
        assert RoleAssignment.objects.filter(
            organization=organization,
            user=user,
            role=role,
            deleted_at__isnull=True,
        ).exists()

    def test_duplicate_membership_raises(self, superadmin_request):
        membership = UserOrganizationFactory(permission_keys=["user:read"])
        role = Role.objects.create(
            organization=membership.organization,
            name="Org Admin",
            description="Org administrator",
            permissions=["user:read"],
            role_type=Role.RoleType.USER_CUSTOM,
            is_active=True,
            created_by=membership.assigned_by,
        )
        serializer = MembershipMutationSerializer(
            data={
                "organization": membership.organization.pk,
                "roles": [str(role.uuid)],
            },
            context={"request": superadmin_request, "user": membership.user},
        )
        with pytest.raises(CustomError) as exc:
            serializer.is_valid(raise_exception=True)
        assert getattr(exc.value, "detail", {}).get("code") == USER_ALREADY_MEMBER


@pytest.mark.django_db
class TestMembershipRemovalSerializer:
    def test_remove_membership(self, superadmin_request):
        membership = UserOrganizationFactory(permission_keys=["user:read"])
        role = Role.objects.create(
            organization=membership.organization,
            name="Org Admin",
            description="Org administrator",
            permissions=["user:read"],
            role_type=Role.RoleType.USER_CUSTOM,
            is_active=True,
            created_by=membership.assigned_by,
        )
        RoleAssignment.objects.create(
            organization=membership.organization,
            user=membership.user,
            role=role,
            assigned_by=membership.assigned_by,
        )
        serializer = MembershipRemovalSerializer(
            data={"organization": membership.organization.pk},
            context={"request": superadmin_request, "user": membership.user},
        )
        assert serializer.is_valid(raise_exception=True)
        serializer.remove()
        assert not UserOrganization.objects.filter(id=membership.id).exists()

    def test_remove_membership_soft_deletes_role_assignments(self, superadmin_request):
        membership = UserOrganizationFactory(permission_keys=["user:read"])
        role = Role.objects.create(
            organization=membership.organization,
            name="Team Specialist",
            description="Team scoped permissions",
            permissions=["teams:read"],
            role_type=Role.RoleType.USER_CUSTOM,
            is_active=True,
            created_by=membership.assigned_by,
        )
        assignment = RoleAssignment.objects.create(
            organization=membership.organization,
            user=membership.user,
            role=role,
            assigned_by=membership.assigned_by,
        )

        serializer = MembershipRemovalSerializer(
            data={"organization": membership.organization.pk},
            context={"request": superadmin_request, "user": membership.user},
        )
        assert serializer.is_valid(raise_exception=True)
        serializer.remove()

        assert not RoleAssignment.objects.filter(pk=assignment.pk).exists()
        archived = RoleAssignment.all_objects.get(pk=assignment.pk)
        assert archived.deleted_at is not None

    def test_remove_membership_blocks_last_owner(self, superadmin_request):
        membership = UserOrganizationFactory(permission_keys=["user:read"])
        owner_role = Role.objects.create(
            organization=membership.organization,
            name=ROLE_ORGANIZATION_OWNER,
            description="Owner template",
            permissions=["organizations:assign_owner"],
            role_type=Role.RoleType.PREDEFINED_CUSTOM,
            is_active=True,
            created_by=membership.assigned_by,
        )
        RoleAssignment.objects.create(
            organization=membership.organization,
            user=membership.user,
            role=owner_role,
            assigned_by=membership.assigned_by,
        )

        serializer = MembershipRemovalSerializer(
            data={"organization": membership.organization.pk},
            context={"request": superadmin_request, "user": membership.user},
        )
        assert serializer.is_valid(raise_exception=True)
        with pytest.raises(serializers.ValidationError):
            serializer.remove()

        assert RoleAssignment.objects.filter(
            organization=membership.organization,
            user=membership.user,
            role=owner_role,
            deleted_at__isnull=True,
        ).exists()
        assert UserOrganization.objects.filter(pk=membership.pk).exists()

    def test_remove_membership_owner_allowed_when_others_exist(self, superadmin_request):
        primary_membership = UserOrganizationFactory(permission_keys=["user:read"])
        owner_role = Role.objects.create(
            organization=primary_membership.organization,
            name=ROLE_ORGANIZATION_OWNER,
            description="Owner template",
            permissions=["organizations:assign_owner"],
            role_type=Role.RoleType.PREDEFINED_CUSTOM,
            is_active=True,
            created_by=primary_membership.assigned_by,
        )
        RoleAssignment.objects.create(
            organization=primary_membership.organization,
            user=primary_membership.user,
            role=owner_role,
            assigned_by=primary_membership.assigned_by,
        )

        secondary_member = UserFactory()
        secondary_membership = UserOrganizationFactory(
            user=secondary_member,
            organization=primary_membership.organization,
            permission_keys=["user:read"],
        )
        RoleAssignment.objects.create(
            organization=primary_membership.organization,
            user=secondary_member,
            role=owner_role,
            assigned_by=secondary_membership.assigned_by,
        )

        serializer = MembershipRemovalSerializer(
            data={"organization": primary_membership.organization.pk},
            context={"request": superadmin_request, "user": primary_membership.user},
        )
        assert serializer.is_valid(raise_exception=True)
        serializer.remove()

        assert not UserOrganization.objects.filter(pk=primary_membership.pk).exists()
        assert not RoleAssignment.objects.filter(
            organization=primary_membership.organization,
            user=primary_membership.user,
            role=owner_role,
            deleted_at__isnull=True,
        ).exists()
        remaining_owner = RoleAssignment.objects.get(
            organization=primary_membership.organization,
            user=secondary_member,
            role=owner_role,
        )
        assert remaining_owner.deleted_at is None

    def test_remove_missing_membership_raises(self, superadmin_request):
        organization = OrganizationFactory()
        user = UserFactory()
        serializer = MembershipRemovalSerializer(
            data={"organization": organization.pk},
            context={"request": superadmin_request, "user": user},
        )
        assert serializer.is_valid(raise_exception=True)
        with pytest.raises(CustomError) as exc:
            serializer.remove()
        assert getattr(exc.value, "detail", {}).get("code") == USER_NOT_MEMBER





