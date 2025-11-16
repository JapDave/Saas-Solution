import pytest
from django.utils import timezone

from apps.agents.models import OrganizationEnabledTool
from apps.knowledge_base.models import Collection
from apps.organizations.tests.factories import OrganizationFactory
from apps.tools.services import validate_tool_configuration


def _seed_tool(organization, tool_key="kb_retriever"):
    OrganizationEnabledTool.objects.create(
        organization=organization,
        tool_key=tool_key,
        enabled_at=timezone.now(),
    )


@pytest.mark.django_db
def test_validate_tool_configuration_with_kb_reference():
    organization = OrganizationFactory()
    _seed_tool(organization, "kb_retriever")
    collection = Collection.objects.create(
        organization=organization,
        name="KB",
        created_by=None,
        updated_by=None,
        state=Collection.CollectionState.ACTIVE,
    )
    payload = {
        "toolKey": "kb_retriever",
        "configuration": {"collection_id": str(collection.uuid), "maxResults": 5},
    }
    cleaned = validate_tool_configuration(payload, organization=organization)
    assert cleaned["toolKey"] == "kb_retriever"
    assert cleaned["configuration"]["collection_id"] == str(collection.uuid)


@pytest.mark.django_db
def test_validate_tool_configuration_invalid_collection():
    organization = OrganizationFactory()
    _seed_tool(organization, "kb_retriever")
    payload = {
        "toolKey": "kb_retriever",
        "configuration": {"collection_id": str(timezone.now().date())},
    }
    with pytest.raises(Exception):
        validate_tool_configuration(payload, organization=organization)
