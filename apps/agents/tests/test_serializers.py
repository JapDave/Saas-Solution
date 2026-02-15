import pytest

from apps.agents.serializers import AgentCreateSerializer, AgentPatchSerializer


def test_agent_create_serializer_validates_name():
    serializer = AgentCreateSerializer(data={"name": "Support Bot", "description": "Help"})
    assert serializer.is_valid(), serializer.errors


def test_agent_patch_serializer_rejects_empty_name():
    serializer = AgentPatchSerializer(data={"name": " "}, partial=True)
    assert not serializer.is_valid()
