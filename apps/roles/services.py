from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from apps.roles.models import Role
from apps.organizations.models import Organization
from apps.roles.constants import (
    ROLE_ORGANIZATION_OWNER,
    ROLE_ORGANIZATION_ADMINISTRATOR,
)


@dataclass
class ServiceResult:
    ok: bool
    role: Role | None = None
    error: str | None = None


@transaction.atomic
def create_organization_owner_role(
    organization: Organization, 
    created_by,
    permissions: list[str],
    account_name: str=ROLE_ORGANIZATION_OWNER,
    account_description: str=None,
    account_is_active: bool=True,
) -> ServiceResult:
    """
    Creates the 'Organization Owner' role specific to a new organization,
    based on the system-wide template role.
    """
    try:
        role = Role.objects.create(
            organization=organization,
            name=account_name,
            description=account_description,
            permissions=permissions,
            role_type=Role.RoleType.PREDEFINED_CUSTOM,
            is_active=account_is_active,
            created_by=created_by,
        )
        return ServiceResult(ok=True, role=role)
    except Exception as e:
        return ServiceResult(ok=False, error=str(e))


def create_account_owner_role():
    """
    Placeholder for creating the 'Account Owner' role.
    """
    # This would be implemented similarly to create_organization_owner_role
    # but likely triggered during Account creation.
    pass
