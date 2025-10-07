import factory
from factory.django import DjangoModelFactory

from apps.organizations.tests.factories import OrganizationFactory
from apps.teams.models import Team, TeamMember
from apps.users.models import UserOrganization
from apps.users.tests.factories import UserFactory


class TeamFactory(DjangoModelFactory):
    """Factory for the Team model."""

    class Meta:
        model = Team

    organization = factory.SubFactory(OrganizationFactory)
    name = factory.Sequence(lambda n: f"Team {n}")
    description = factory.Faker("sentence", nb_words=6)
    configurations = factory.LazyFunction(dict)

    @factory.lazy_attribute
    def created_by(self):
        org_creator = getattr(self.organization, "created_by", None)
        if org_creator:
            return org_creator
        account_creator = getattr(getattr(self.organization, "account", None), "created_by", None)
        return account_creator

    @factory.lazy_attribute
    def updated_by(self):
        return self.created_by


class TeamMemberFactory(DjangoModelFactory):
    """Factory for the TeamMember model."""

    class Meta:
        model = TeamMember

    team = factory.SubFactory(TeamFactory)
    user = factory.SubFactory(UserFactory)

    @factory.lazy_attribute
    def assigned_by(self):
        return self.team.created_by or self.user

    role_keys = factory.List([])

    @factory.post_generation
    def ensure_membership(self, create, extracted, **kwargs):
        if not create:
            return
        org = self.team.organization
        if not UserOrganization.objects.filter(user=self.user, organization=org).exists():
            UserOrganization.objects.create(
                user=self.user,
                organization=org,
                assigned_by=self.assigned_by,
            )


__all__ = ["TeamFactory", "TeamMemberFactory"]
