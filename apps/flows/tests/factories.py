import factory

from apps.flows.models import Flow, FlowVersion
from apps.organizations.tests.factories import OrganizationFactory
from apps.users.tests.factories import UserFactory


class FlowFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Flow

    organization = factory.SubFactory(OrganizationFactory)
    name = factory.Sequence(lambda n: f"Flow {n}")
    description = factory.Faker("sentence")
    flow_configurations = factory.LazyFunction(lambda: {"autoRetry": True})
    created_by = factory.SubFactory(UserFactory)
    updated_by = factory.SelfAttribute("created_by")


class FlowVersionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FlowVersion

    flow = factory.SubFactory(FlowFactory)
    version_number = factory.Sequence(lambda n: n + 1)
    name = factory.LazyAttribute(lambda obj: obj.flow.name)
    description = factory.Faker("sentence")
    flow_configurations = factory.LazyFunction(lambda: {"autoRetry": True})
    flow_json = factory.LazyFunction(
        lambda: {
            "nodes": [
                {
                    "id": "trigger",
                    "type": "trigger",
                    "position": {"x": 0, "y": 0},
                    "data": {"triggerType": "webhook", "eventType": "demo"},
                }
            ],
            "edges": [],
            "viewport": {"x": 0, "y": 0, "zoom": 1.0},
        }
    )
    state = FlowVersion.FlowVersionState.DRAFT
    created_by = factory.SelfAttribute("flow.created_by")
