import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.tests.factories import AccountFactory
from apps.channels.models import Channel
from apps.roles.management.commands.initialize_roles import Command as InitializeRoles
from apps.organizations.tests.factories import OrganizationFactory
from apps.users.models import UserOrganization
from apps.users.tests.factories import UserFactory


@pytest.fixture
def channel_context(db):
    InitializeRoles().handle()
    user = UserFactory()
    account = AccountFactory(created_by=user)
    organization = OrganizationFactory(account=account, created_by=user)
    UserOrganization.objects.create(
        user=user,
        organization=organization,
        permission_keys=[
            "channels:create",
            "channels:read",
            "channels:update",
            "channels:delete",
            "channels:activate",
        ],
        assigned_by=user,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return {"client": client, "organization": organization}


def _channel_payload():
    return {
        "channel_type": "web_chat",
        "name": "Support Chat",
        "configurations": {
            "webChatDisplayName": "Support Chat",
            "webChatPosition": "right",
            "webChatDirection": "rtl",
            "webChatTheme": "standard",
            "webChatSupportedLanguages": ["ar", "en"],
            "webChatDefaultLanguage": "ar",
            "webChatSize": 1,
            "webChatTitleText": "Welcome",
            "webChatAllowRenderingMedia": True,
            "webChatAllowSendingMedia": False,
            "webChatAllowNavMainMenu": False,
            "webChatAllowNavPreviousMenu": False,
            "webChatSessionDuration": 600,
        },
    }


@pytest.mark.django_db
def test_create_web_chat_channel(channel_context):
    url = reverse("organization-channels-list", kwargs={"organization_uuid": channel_context["organization"].uuid})
    response = channel_context["client"].post(url, _channel_payload(), format="json")
    assert response.status_code == status.HTTP_201_CREATED
    assert Channel.objects.count() == 1


@pytest.mark.django_db
def test_invalid_configuration_rejected(channel_context):
    url = reverse("organization-channels-list", kwargs={"organization_uuid": channel_context["organization"].uuid})
    payload = {
        "channel_type": "web_chat",
        "name": "Broken Chat",
        "configurations": {
            "webChatDisplayName": "Broken",
            "webChatPosition": "center",
        },
    }
    response = channel_context["client"].post(url, payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
