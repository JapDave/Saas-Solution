from __future__ import annotations
from typing import TYPE_CHECKING

from apps.roles.constants import SYSTEM_ROLES

if TYPE_CHECKING:
    from apps.users.models import User
    from uuid import UUID


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
    if not user or not hasattr(user, "is_authenticated") or not user.is_authenticated:
        return False

    is_system_role = role_name in SYSTEM_ROLES

    if not is_system_role and organization_uuid is None:
        raise ValueError(
            f"An organization_uuid must be provided to check for the non-system role: '{role_name}'"
        )

    assignments = user.role_assignments.filter(role__name=role_name, is_active=True)
    print(f"Assignments for user {user} and role '{role_name}': {assignments.exists()}")
    print(f"Is system role: {is_system_role}, organization_uuid: {organization_uuid}")
    if organization_uuid:
        return assignments.filter(organization__uuid=organization_uuid).exists()
    
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
