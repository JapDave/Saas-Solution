import pytest
from django.utils import timezone

from apps.agents.models import OrganizationEnabledLLM
from apps.llms.serializers import OrganizationEnabledLLMSerializer
from apps.organizations.tests.factories import OrganizationFactory


@pytest.mark.django_db
def test_enabled_llm_serializer():
    organization = OrganizationFactory()
    record = OrganizationEnabledLLM.objects.create(
        organization=organization,
        model_key="gpt-4o-mini",
        model_provider="OpenAI",
        enabled_at=timezone.now(),
    )
    data = OrganizationEnabledLLMSerializer(record).data
    assert data["model_key"] == "gpt-4o-mini"
    assert data["disabled_at"] is None
