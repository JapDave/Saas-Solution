import pytest
from rest_framework.test import APIRequestFactory

from apps.common.exceptions import (
    SubscriptionLimitExceeded,
    TeamNameExists,
    TeamSizeLimitExceeded,
    UserAlreadyMember,
    UserNotMember,
)
from apps.organizations.tests.factories import OrganizationFactory
from apps.teams.models import TeamMember
from apps.teams.serializers import (
    TeamCreateSerializer,
    TeamMemberMutationSerializer,
    TeamMemberRemovalSerializer,
    TeamUpdateSerializer,
)
from apps.teams.tests.factories import TeamFactory, TeamMemberFactory
from apps.users.tests.factories import SuperUserFactory, UserFactory, UserOrganizationFactory


factory = APIRequestFactory()


@pytest.mark.django_db
class TestTeamCreateSerializer:
    def test_create_success(self):
        owner = SuperUserFactory()
        organization = OrganizationFactory(created_by=owner)
        request = factory.post("/api/teams/")
        request.user = owner
        serializer = TeamCreateSerializer(
            data={"organization": organization.id, "name": "Support", "description": ""},
            context={"request": request},
        )
        assert serializer.is_valid(), serializer.errors
        team = serializer.save()
        assert team.name == "Support"
        assert team.created_by == owner

    def test_duplicate_name(self):
        owner = SuperUserFactory()
        organization = OrganizationFactory(created_by=owner)
        TeamFactory(organization=organization, name="Growth", created_by=owner, updated_by=owner)
        request = factory.post("/api/teams/")
        request.user = owner
        serializer = TeamCreateSerializer(
            data={"organization": organization.id, "name": "growth"},
            context={"request": request},
        )
        with pytest.raises(TeamNameExists):
            serializer.is_valid(raise_exception=True)

    def test_subscription_limit(self, settings):
        owner = SuperUserFactory()
        organization = OrganizationFactory(created_by=owner)
        settings.TEAM_DEFAULT_LIMITS = {"max_teams": 1}
        TeamFactory(organization=organization, name="Initial", created_by=owner, updated_by=owner)
        request = factory.post("/api/teams/")
        request.user = owner
        serializer = TeamCreateSerializer(
            data={"organization": organization.id, "name": "Overflow"},
            context={"request": request},
        )
        with pytest.raises(SubscriptionLimitExceeded):
            serializer.is_valid(raise_exception=True)


@pytest.mark.django_db
class TestTeamUpdateSerializer:
    def test_update_description(self):
        team = TeamFactory()
        request = factory.patch("/api/teams/")
        request.user = team.created_by
        serializer = TeamUpdateSerializer(
            instance=team,
            data={"description": "Updated"},
            partial=True,
            context={"request": request},
        )
        assert serializer.is_valid(), serializer.errors
        updated = serializer.save()
        assert updated.description == "Updated"


@pytest.mark.django_db
class TestTeamMemberMutationSerializer:
    def test_add_member(self):
        team = TeamFactory()
        target_user = UserFactory()
        UserOrganizationFactory(user=target_user, organization=team.organization)
        request = factory.post(f"/api/teams/{team.uuid}/members/")
        request.user = team.created_by
        serializer = TeamMemberMutationSerializer(
            data={"user": str(target_user.uuid)},
            context={"request": request, "team": team},
        )
        assert serializer.is_valid(), serializer.errors
        membership = serializer.save()
        assert TeamMember.objects.filter(team=team, user=target_user, deleted_at__isnull=True).exists()
        assert membership.assigned_by == team.created_by

    def test_member_limit_enforced(self, settings):
        settings.TEAM_DEFAULT_LIMITS = {"max_team_members": 1}
        team = TeamFactory()
        existing = TeamMemberFactory(team=team)
        request = factory.post(f"/api/teams/{team.uuid}/members/")
        request.user = team.created_by
        serializer = TeamMemberMutationSerializer(
            data={"user": str(existing.user.uuid)},
            context={"request": request, "team": team},
        )
        with pytest.raises(UserAlreadyMember):
            serializer.is_valid(raise_exception=True)

        other_user = UserFactory()
        UserOrganizationFactory(user=other_user, organization=team.organization)
        serializer = TeamMemberMutationSerializer(
            data={"user": str(other_user.uuid)},
            context={"request": request, "team": team},
        )
        with pytest.raises(TeamSizeLimitExceeded):
            serializer.is_valid(raise_exception=True)


@pytest.mark.django_db
class TestTeamMemberRemovalSerializer:
    def test_remove_member(self):
        membership = TeamMemberFactory()
        team = membership.team
        request = factory.delete(f"/api/teams/{team.uuid}/members/{membership.user.uuid}/")
        request.user = team.created_by
        serializer = TeamMemberRemovalSerializer(
            data={"user": str(membership.user.uuid)},
            context={"request": request, "team": team},
        )
        assert serializer.is_valid(), serializer.errors
        serializer.remove()
        membership.refresh_from_db()
        assert membership.deleted_at is not None

    def test_remove_non_member(self):
        team = TeamFactory()
        user = UserFactory()
        request = factory.delete(f"/api/teams/{team.uuid}/members/{user.uuid}/")
        request.user = team.created_by
        serializer = TeamMemberRemovalSerializer(
            data={"user": str(user.uuid)},
            context={"request": request, "team": team},
        )
        with pytest.raises(UserNotMember):
            serializer.is_valid(raise_exception=True)


__all__ = []
