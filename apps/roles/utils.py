from __future__ import annotations
from typing import TYPE_CHECKING
from uuid import UUID

from django.db.models import Q

from apps.roles.constants import ROLE_SAAS_ADMINISTRATOR, SYSTEM_ROLES

if TYPE_CHECKING:
    from apps.users.models import User
    from uuid import UUID


def _split_org_identifier(value):
    """Return tuple of (uuid_str, int_id) based on the provided identifier."""
    if value is None:
        return (None, None)
    if isinstance(value, UUID):
        return (str(value), None)
    if isinstance(value, int):
        return (None, value)
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return (None, None)
        if candidate.isdigit():
            try:
                return (None, int(candidate))
            except ValueError:
                return (None, None)
        try:
            return (str(UUID(candidate)), None)
        except ValueError:
            return (None, None)
    return (None, None)



def has_role(
    user: User,
    role_name: str,
    organization_uuid: UUID | str | None = None
) -> bool:
    """
    Checks if a user has a specific role, either globally or within an organization.

    Args:
        user: The user instance to check.
        role_name: The name of the role (e.g., "Organization Owner").
        organization_uuid: Optional. The UUID of the organization to check against.
                           If None, checks for a global role (e.g. "SaaS Administrator").

    Returns:
        True if the user has the role, False otherwise.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False

    normalised_name = (role_name or "").strip()
    if not normalised_name:
        return False

    is_system_role = normalised_name in SYSTEM_ROLES

    if not is_system_role and organization_uuid is None:
        raise ValueError(
            f"An organization_uuid must be provided to check for the non-system role: '{normalised_name}'"
        )

    assignments = user.role_assignments.filter(role__name=normalised_name, is_active=True)

    if organization_uuid is not None:
        org_uuid, org_id = _split_org_identifier(organization_uuid)
        org_filters = Q()
        if org_uuid:
            org_filters |= Q(organization__uuid=org_uuid)
        if org_id is not None:
            org_filters |= Q(organization_id=org_id)
        if not org_filters:
            return False
        return assignments.filter(org_filters).exists()

    return assignments.filter(organization__isnull=True).exists()


def has_permission(
    user: User,
    permission_key: str,
    organization_uuid: UUID | str
) -> bool:
    """
    Checks if a user has a specific permission via their assigned roles,
    within the context of a specific organization.

    This check includes permissions from roles assigned directly to the
    organization, as well as permissions from global (system) roles.

    Args:
        user: The user instance to check.
        permission_key: The permission string (e.g., "users:invite").
        organization_uuid: The UUID of the organization to check against.

    Returns:
        True if the user has the permission, False otherwise.
    """
    if not user or not hasattr(user, "is_authenticated") or not user.is_authenticated:
        return False

    # Find active assignments for this user that are either for the specified
    # organization OR are global (system) roles.
    assignments = user.role_assignments.filter(
        organization__uuid=organization_uuid,
        is_active=True,
    )
    return assignments.filter(role__permissions__contains=[permission_key]).exists()
