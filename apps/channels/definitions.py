"""
Static metadata describing supported channel types and their configuration defaults.
The full validation logic lives in ``apps.channels.validators``; this module centralises
enumerations and reusable constants so other modules (services, serializers, docs) can
depend on a single source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable


CHANNEL_TYPE_WEB_CHAT = "web_chat"
CHANNEL_TYPE_WHATSAPP = "whatsapp"
CHANNEL_TYPE_X = "x"

CHANNEL_TYPE_CHOICES = (
    (CHANNEL_TYPE_WEB_CHAT, "Web Chat"),
    (CHANNEL_TYPE_WHATSAPP, "WhatsApp"),
    (CHANNEL_TYPE_X, "X / Twitter"),
)

CHANNEL_INSTANCE_PERMISSION_KEYS = {
    "channel:read",
    "channel:send_message",
    "channel:manage",
}


@dataclass(frozen=True)
class ConfigField:
    field_type: str
    required: bool
    default: Any = None
    choices: Iterable[str] | None = None
    minimum: float | None = None
    maximum: float | None = None
    allow_blank: bool = False


CHANNEL_CONFIGURATION_SCHEMAS: Dict[str, Dict[str, ConfigField]] = {
    CHANNEL_TYPE_WEB_CHAT: {
        "webChatDisplayName": ConfigField("string", True),
        "webChatPosition": ConfigField("enum", True, default="right", choices=["left", "right"]),
        "webChatDirection": ConfigField("enum", True, default="rtl", choices=["ltr", "rtl"]),
        "webChatTheme": ConfigField("enum", True, default="standard", choices=["standard", "light", "dark"]),
        "webChatSupportedLanguages": ConfigField("language_list", True, default=["ar", "en"]),
        "webChatDefaultLanguage": ConfigField("language", True, default="ar"),
        "webChatSize": ConfigField("integer", True, default=1, minimum=1, maximum=3),
        "webChatHeaderLogoUrl": ConfigField("url", False),
        "webChatAgentLogoUrl": ConfigField("url", False),
        "webChatTitleText": ConfigField("string", True),
        "webChatSubtitleText": ConfigField("string", False, allow_blank=True),
        "webChatFooterText": ConfigField("string", False, allow_blank=True),
        "webChatHeaderSuperText": ConfigField("string", False, allow_blank=True),
        "webChatAllowRenderingMedia": ConfigField("boolean", True, default=True),
        "webChatAllowSendingMedia": ConfigField("boolean", True, default=False),
        "webChatAllowNavMainMenu": ConfigField("boolean", True, default=False),
        "webChatAllowNavPreviousMenu": ConfigField("boolean", True, default=False),
        "webChatSessionDuration": ConfigField("integer", True, default=1800, minimum=60, maximum=86400),
        "webChatPrimaryColor": ConfigField("color", False),
        "webChatSecondaryColor": ConfigField("color", False),
        "webChatSurveys": ConfigField("array", False, default=[]),
        "webChatForms": ConfigField("array", False, default=[]),
    },
    CHANNEL_TYPE_WHATSAPP: {
        "whatsappDisplayName": ConfigField("string", True),
        "whatsappPhoneNumber": ConfigField("phone", True),
        "whatsappProfilePicture": ConfigField("url", True),
        "whatsappToken": ConfigField("system_string", True),
        "whatsappApprovalStatus": ConfigField(
            "enum", True, default="pending", choices=["pending", "approved", "rejected", "expired"]
        ),
    },
    CHANNEL_TYPE_X: {
        "xDisplayName": ConfigField("string", True),
        "xHandle": ConfigField("handle", True),
        "xProfilePicture": ConfigField("url", True),
    },
}


DEFAULT_SUBSCRIPTION_CHANNEL_CONFIG = {
    CHANNEL_TYPE_WEB_CHAT: {"enabled": True, "maxInstances": 1},
    CHANNEL_TYPE_WHATSAPP: {"enabled": False, "maxInstances": 1},
    CHANNEL_TYPE_X: {"enabled": False, "maxInstances": 1},
}
