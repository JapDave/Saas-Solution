import pytest
from django.core.exceptions import ValidationError

from apps.teams.models import Team, TeamMember
from apps.teams.tests.factories import TeamFactory, TeamMemberFactory
from apps.users.tests.factories import UserFactory


@pytest.mark.django_db
class TestTeamModel:
    def test_str(self):
        team = TeamFactory(name="Support Squad")
        assert str(team) == f"Support Squad (org={team.organization_id})"

    def test_unique_name_case_sensitive(self):
        team = TeamFactory(name="Growth")
        dup = Team(
            organization=team.organization,
            name="growth",
            description="",
            created_by=team.created_by,
            updated_by=team.updated_by,
        )
        dup.full_clean()

    def test_configurations_must_be_dict(self):
        team = TeamFactory()
        team.configurations = ["not", "a", "dict"]
        with pytest.raises(ValidationError):
            team.full_clean()


@pytest.mark.django_db
class TestTeamMemberModel:
    def test_membership_requires_org_membership(self):
        team = TeamFactory()
        outsider = UserFactory()
        membership = TeamMember(team=team, user=outsider, assigned_by=team.created_by)
        with pytest.raises(ValidationError):
            membership.full_clean()

    def test_factory_ensures_membership(self):
        membership = TeamMemberFactory()
        assert membership.team.memberships.filter(user=membership.user).exists()

    def test_deactivate(self):
        membership = TeamMemberFactory()
        membership.deactivate()
        membership.refresh_from_db()
        assert membership.is_active is False


__all__ = []
