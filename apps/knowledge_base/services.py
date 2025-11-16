from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from apps.common.exceptions import CustomError, INSUFFICIENT_PERMISSIONS, SUBSCRIPTION_LIMIT_EXCEEDED
from apps.knowledge_base.models import Collection
from apps.subscriptions.services import get_subscription_configuration
from apps.users.services import resolve_effective_permission_keys

KB_MODULE_KEY = "KNOWLEDGE_BASE_MANAGEMENT"


@dataclass(frozen=True)
class KnowledgeBaseLimit:
    max_collections: int
    max_resources_per_collection: int


DEFAULT_LIMITS = KnowledgeBaseLimit(max_collections=3, max_resources_per_collection=10)


def resolve_kb_limits(organization) -> KnowledgeBaseLimit:
    config = get_subscription_configuration(organization, KB_MODULE_KEY) or {}
    return KnowledgeBaseLimit(
        max_collections=int(config.get("kb.collections.max", DEFAULT_LIMITS.max_collections)),
        max_resources_per_collection=int(
            config.get("kb.resources_per_collection", DEFAULT_LIMITS.max_resources_per_collection)
        ),
    )


def enforce_collection_limit(organization):
    limits = resolve_kb_limits(organization)
    count = Collection.objects.filter(organization=organization).count()
    if count >= limits.max_collections:
        raise CustomError(
            code="KB_LIMIT_EXCEEDED",
            status_code=409,
            detail=f"{count}/{limits.max_collections} collections in use.",
        )


def enforce_resource_limit(collection):
    limits = resolve_kb_limits(collection.organization)
    count = collection.resources.count()
    if count >= limits.max_resources_per_collection:
        raise CustomError(
            code="KB_LIMIT_EXCEEDED",
            status_code=409,
            detail=f"{count}/{limits.max_resources_per_collection} resources used in this collection.",
        )


def user_has_kb_permission(user, organization, permission_key: str) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    permissions = {perm.lower() for perm in resolve_effective_permission_keys(user, organization.id)}
    target = (permission_key or "").lower()
    return target in permissions or "kb:admin" in permissions


def ensure_kb_permission(user, organization, permission_key: str):
    if not user_has_kb_permission(user, organization, permission_key):
        raise CustomError(code=INSUFFICIENT_PERMISSIONS, status_code=403, detail="Insufficient permissions.")

