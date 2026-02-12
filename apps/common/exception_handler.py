from __future__ import annotations
from typing import Any, Mapping, Optional, TypedDict

from django.conf import settings
from django.http import Http404
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.exceptions import ValidationError, PermissionDenied, NotFound
from rest_framework.response import Response

# Shared/base codes (your concrete coded exceptions will pass through untouched)
from .exceptions import INSUFFICIENT_PERMISSIONS

# Generic fallbacks if no domain match is found
GENERIC_NOT_FOUND = "NOT_FOUND"
GENERIC_INVALID = "INVALID_DATA"


class DomainConf(TypedDict, total=False):
    not_found: str
    invalid: str
    prefixes: list[str]  # module path substrings used to detect the domain


# Built-in defaults — extend/override in settings.COMMON_EXCEPTION_DOMAINS
DEFAULT_DOMAIN_MAP: dict[str, DomainConf] = {
    "accounts": {
        "not_found": "ACCOUNT_NOT_FOUND",
        "invalid": "INVALID_ACCOUNT_DATA",
        "prefixes": ["apps.accounts."],
    },
    "organizations": {
        "not_found": "ORGANIZATION_NOT_FOUND",
        "invalid": "INVALID_ORGANIZATION_DATA",
        "prefixes": ["apps.organizations.", "apps.organization."],
    },
    "users": {
        "not_found": "USER_NOT_FOUND",
        "invalid": "INVALID_USER_DATA",
        "prefixes": ["apps.users."],
    },
    "teams": {
        "not_found": "TEAM_NOT_FOUND",
        "invalid": "INVALID_TEAM_DATA",
        "prefixes": ["apps.teams."],
    },
    "roles": {
        "not_found": "ROLE_NOT_FOUND",
        "invalid": "INVALID_ROLE_DATA",
        "prefixes": ["apps.roles."],
    },
    "files": {
        "not_found": "FILE_NOT_FOUND",
        "invalid": "INVALID_FILE_DATA",
        "prefixes": ["apps.files."],
    },
    "subscriptions": {
        "not_found": "SUBSCRIPTION_NOT_FOUND",
        "invalid": "INVALID_SUBSCRIPTION_DATA",
        "prefixes": ["apps.subscriptions."],
    },
    # For products vs modules, rely on per-view ERROR_DOMAIN hints
    "products": {
        "not_found": "PRODUCT_NOT_FOUND",
        "invalid": "INVALID_PRODUCT_DATA",
        "prefixes": ["apps.products."],
    },
    "modules": {
        "not_found": "MODULE_NOT_FOUND",
        "invalid": "INVALID_MODULE_DATA",
        "prefixes": ["apps.products."],
    },
    "agents": {
        "not_found": "AGENT_NOT_FOUND",
        "invalid": "INVALID_AGENT_DATA",
        "prefixes": ["apps.agents."],
    },
    "channels": {
        "not_found": "CHANNEL_NOT_FOUND",
        "invalid": "INVALID_CHANNEL_CONFIGURATION",
        "prefixes": ["apps.channels."],
    },
}


def _load_domain_map() -> dict[str, DomainConf]:
    """
    Merge defaults with optional overrides from settings.COMMON_EXCEPTION_DOMAINS.

    Example (settings.py):
    COMMON_EXCEPTION_DOMAINS = {
        "billing": {
            "not_found": "SUBSCRIPTION_NOT_FOUND",
            "invalid": "INVALID_SUBSCRIPTION_DATA",
            "prefixes": ["apps.billing.", "myproj.billing."],
        },
        # you can also override existing ones:
        "accounts": {
            "prefixes": ["apps.accounts.", "myproj.accounts."],
        },
    }
    """
    user_map = getattr(settings, "COMMON_EXCEPTION_DOMAINS", {}) or {}
    merged = dict(DEFAULT_DOMAIN_MAP)
    for domain, conf in user_map.items():
        base = merged.get(domain, {})
        merged[domain] = {
            **base,
            **conf,
            "prefixes": conf.get("prefixes", base.get("prefixes", [])),
        }
    return merged


_DOMAIN_MAP = _load_domain_map()


def _resolve_domain(view_module: str, explicit: Optional[str] = None) -> tuple[str, str]:
    """
    Return (NOT_FOUND_CODE, INVALID_CODE) for a given view.

    Priority:
      1) Explicit per-view hint: view.ERROR_DOMAIN = "<domain>"
      2) Longest matching module prefix from _DOMAIN_MAP
      3) Generic fallback
    """
    if explicit:
        conf = _DOMAIN_MAP.get(explicit)
        if conf:
            return conf.get("not_found", GENERIC_NOT_FOUND), conf.get("invalid", GENERIC_INVALID)

    vm = (view_module or "").lower()
    best_domain: Optional[str] = None
    best_len = -1

    for domain, conf in _DOMAIN_MAP.items():
        for pref in conf.get("prefixes", []) or []:
            p = pref.lower()
            if p in vm and len(p) > best_len:
                best_len = len(p)
                best_domain = domain

    if best_domain:
        conf = _DOMAIN_MAP[best_domain]
        return conf.get("not_found", GENERIC_NOT_FOUND), conf.get("invalid", GENERIC_INVALID)

    return GENERIC_NOT_FOUND, GENERIC_INVALID


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """
    Normalize DRF errors so every response has {"code": "..."}.
    - Custom coded exceptions (that already set {"code": ...}) pass through unchanged.
    - Maps PermissionDenied → INSUFFICIENT_PERMISSIONS
    - Maps NotFound/Http404 → domain NOT_FOUND
    - Maps ValidationError → domain INVALID
    - As a safety net, *any* 404 response (even from unusual exceptions) is mapped to domain NOT_FOUND.
    """
    response = drf_exception_handler(exc, context)
    if response is None:
        return Response({"code": "ERROR", "message": "Internal server error."}, status=500)

    # Already-coded payloads pass through unchanged
    if isinstance(response.data, Mapping) and "code" in response.data:
        return response

    view = context.get("view")
    view_module = getattr(view, "__module__", "") if view else ""
    explicit_domain = getattr(view, "ERROR_DOMAIN", None)
    not_found_code, invalid_code = _resolve_domain(view_module, explicit_domain)

    # Permission
    if isinstance(exc, PermissionDenied):
        detail = response.data.get("detail", "Permission denied") if isinstance(response.data, Mapping) else "Permission denied"
        response.data = {"code": INSUFFICIENT_PERMISSIONS, "message": detail}
        return response

    # Not found by exception type
    if isinstance(exc, (NotFound, Http404)):
        detail = response.data.get("detail", "Not found") if isinstance(response.data, Mapping) else "Not found"
        response.data = {"code": not_found_code, "message": detail}
        return response

    # Validation
    if isinstance(exc, ValidationError):
        # If a ValidationError already carries a coded payload, keep it.
        if isinstance(response.data, Mapping) and "code" in response.data:
            return response
        errors = response.data if isinstance(response.data, Mapping) else {"detail": response.data}
        response.data = {"code": invalid_code, "errors": errors}
        return response

    # Safety net: any 404 response becomes domain NOT_FOUND
    if response.status_code == 404:
        detail = response.data.get("detail", "Not found") if isinstance(response.data, Mapping) else "Not found"
        response.data = {"code": not_found_code, "message": detail}
        return response

    # Fallback: wrap unknown shapes
    data = response.data
    if isinstance(data, Mapping):
        response.data = {"code": "ERROR", **data}
    else:
        response.data = {"code": "ERROR", "message": data}
    return response
