import factory

from apps.integrations.models import Integration
from apps.organizations.tests.factories import OrganizationFactory
from apps.users.tests.factories import UserFactory


class IntegrationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Integration

    organization = factory.SubFactory(OrganizationFactory)
    integration_type = Integration.IntegrationType.API
    name = factory.Sequence(lambda n: f"Integration {n}")
    description = "Demo integration"
    url = "https://api.example.com/resources/{resourceId}"
    method = "GET"
    headers = factory.LazyFunction(lambda: [{"key": "Authorization", "value": "Bearer demo"}])
    parameters = factory.LazyFunction(lambda: [{"key": "resourceId", "name": "Resource ID", "type": "path", "required": True, "description": ""}])
    response_mappings = factory.LazyFunction(lambda: [{"key": "result", "name": "Result", "jsonPath": "$.data"}])
    created_by = factory.SubFactory(UserFactory)
    updated_by = factory.SelfAttribute("created_by")

    @factory.post_generation
    def setup_credentials(self, create, extracted, **kwargs):
        if not create:
            return
        if self.integration_type == Integration.IntegrationType.WEBHOOK:
            self.regenerate_webhook_credentials()
            self.save()

