from __future__ import annotations

from dataclasses import dataclass
from typing import Set

from django.db import transaction
from django.db.models import Q

from apps.roles.models import Role, RoleAssignment
from apps.users.models import UserOrganization
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


def resolve_user_permissions(*, user, organization_id: int) -> Set[str]:
    """Return permission keys granted to `user` for the organization."""

    if not user or not getattr(user, "is_authenticated", False):
        return set()

    assignments = (
        user.role_assignments.filter(is_active=True)
        .select_related("role")
        .filter(Q(organization__isnull=True) | Q(organization_id=organization_id))
    )

    permissions: Set[str] = set()
    for assignment in assignments:
        role_permissions = assignment.role.permissions or []
        for permission in role_permissions:
            if not isinstance(permission, str):
                continue
            value = permission.strip()
            if value:
                permissions.add(value.lower())
    return permissions



def _ensure_membership(*, user, organization, assigned_by):
    membership = UserOrganization.all_objects.filter(
        user=user,
        organization=organization,
    ).order_by('-created_at').first()
    if membership:
        updates = False
        if membership.deleted_at is not None:
            membership.deleted_at = None
            updates = True
        if not membership.is_active:
            membership.is_active = True
            updates = True
        if membership.assigned_by_id != getattr(assigned_by, 'id', None):
            membership.assigned_by = assigned_by
            updates = True
        if updates:
            membership.save(update_fields=[
                'deleted_at',
                'is_active',
                'assigned_by',
                'updated_at',
            ])
        return membership

    membership = UserOrganization(
        user=user,
        organization=organization,
        assigned_by=assigned_by,
        permission_keys=[],
    )
    membership.full_clean()
    membership.save()
    return membership


@transaction.atomic
def ensure_organization_owner_role(*, organization, created_by):
    role = Role.objects.filter(
        organization=organization,
        name=ROLE_ORGANIZATION_OWNER,
        is_active=True,
        deleted_at__isnull=True,
    ).first()
    if role:
        return role

    template = Role.objects.filter(
        organization__isnull=True,
        name=ROLE_ORGANIZATION_OWNER,
    ).first()
    permissions = template.permissions if template else []
    result = create_organization_owner_role(
        organization=organization,
        created_by=created_by,
        permissions=permissions,
        account_description=getattr(template, 'description', None),
    )
    if not result.ok or not result.role:
        raise RuntimeError(result.error or 'Failed to create organization owner role')
    return result.role


@transaction.atomic
def assign_organization_owner(*, organization, user, assigned_by):
    role = ensure_organization_owner_role(organization=organization, created_by=assigned_by)
    _ensure_membership(user=user, organization=organization, assigned_by=assigned_by)

    assignment = RoleAssignment.all_objects.filter(
        user=user,
        organization=organization,
        role=role,
    ).order_by('-created_at').first()
    if assignment:
        if assignment.deleted_at is not None or not assignment.is_active:
            assignment.deleted_at = None
            assignment.is_active = True
            assignment.assigned_by = assigned_by
            assignment.save(update_fields=['deleted_at', 'is_active', 'assigned_by', 'updated_at'])
        return assignment

    assignment = RoleAssignment(
        organization=organization,
        user=user,
        role=role,
        assigned_by=assigned_by,
    )
    assignment.full_clean()
    assignment.save()
    return assignment


@transaction.atomic
def remove_organization_owner(*, organization, user, allow_last: bool = False):
    assignment = RoleAssignment.objects.filter(
        organization=organization,
        user=user,
        role__name=ROLE_ORGANIZATION_OWNER,
    ).first()
    if not assignment:
        return None

    if not allow_last:
        remaining = RoleAssignment.objects.filter(
            organization=organization,
            role__name=ROLE_ORGANIZATION_OWNER,
            is_active=True,
            deleted_at__isnull=True,
        ).exclude(pk=assignment.pk).exists()
        if not remaining:
            raise ValueError('Organization must retain at least one owner')

    assignment.delete()
    return assignment


@transaction.atomic
def transfer_organization_owner(*, organization, new_owner, assigned_by, current_owner=None):
    assignment = assign_organization_owner(
        organization=organization,
        user=new_owner,
        assigned_by=assigned_by,
    )

    previous_owner = current_owner or assigned_by
    if previous_owner and getattr(previous_owner, 'id', None) != getattr(new_owner, 'id', None):
        try:
            remove_organization_owner(
                organization=organization,
                user=previous_owner,
                allow_last=False,
            )
        except ValueError:
            # If we cannot remove the previous owner (e.g., they are the last owner),
            # leave the newly assigned owner in place but surface the error.
            raise
    return assignment
