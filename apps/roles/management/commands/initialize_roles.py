from __future__ import annotations

from typing import Iterable, List

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.roles.constants import (
    ROLE_ACCOUNT_ADMINISTRATOR,
    ROLE_ACCOUNT_OWNER,
    ROLE_ORGANIZATION_ADMINISTRATOR,
    ROLE_ORGANIZATION_OWNER,
    ROLE_PERMISSION_TEMPLATES,
    ROLE_SAAS_ACCOUNT_MANAGER,
    ROLE_SAAS_ADMINISTRATOR,
)
from apps.roles.models import Role


def _normalize_permissions(keys: Iterable[str]) -> List[str]:
    normalized: List[str] = []
    for key in keys or []:
        if not isinstance(key, str):
            continue
        value = key.strip().lower()
        if not value:
            continue
        if value not in normalized:
            normalized.append(value)
    return normalized


class Command(BaseCommand):
    help = "Initializes the database with immutable system and user role templates."

    ROLE_DEFINITIONS = (
        {
            "name": ROLE_SAAS_ADMINISTRATOR,
            "role_type": Role.RoleType.SYSTEM,
            "description": "Full platform access across all accounts, organizations, and modules.",
        },
        {
            "name": ROLE_SAAS_ACCOUNT_MANAGER,
            "role_type": Role.RoleType.SYSTEM,
            "description": "Manages assigned accounts and visibility into their organizations and users.",
        },
        {
            "name": ROLE_ACCOUNT_OWNER,
            "role_type": Role.RoleType.USER,
            "description": "Account-level template with full control over account resources.",
        },
        {
            "name": ROLE_ACCOUNT_ADMINISTRATOR,
            "role_type": Role.RoleType.USER,
            "description": "Account-level administrative template with scoped management capabilities.",
        },
        {
            "name": ROLE_ORGANIZATION_OWNER,
            "role_type": Role.RoleType.USER,
            "description": "Organization template with ownership and full management rights.",
        },
        {
            "name": ROLE_ORGANIZATION_ADMINISTRATOR,
            "role_type": Role.RoleType.USER,
            "description": "Organization template for day-to-day administration duties.",
        },
    )

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Starting role initialization...")

        for definition in self.ROLE_DEFINITIONS:
            role_name = definition["name"]
            role_type = definition["role_type"]
            description = definition["description"]
            template_permissions = ROLE_PERMISSION_TEMPLATES.get(role_name, ())
            permissions = _normalize_permissions(template_permissions)

            role, created = Role.objects.update_or_create(
                name=role_name,
                organization__isnull=True,
                role_type=role_type,
                defaults={
                    "description": description,
                    "permissions": permissions,
                    "is_active": True,
                },
            )

            action = "created" if created else "updated"
            self.stdout.write(self.style.SUCCESS(f"Role '{role.name}' {action}."))

        self.stdout.write(self.style.SUCCESS("Role initialization complete."))
