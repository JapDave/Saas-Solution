from django.core.management.base import BaseCommand
from django.db import transaction

from apps.roles.models import Role

from apps.roles.constants import (
    ROLE_SAAS_ADMINISTRATOR,
    ROLE_SAAS_ACCOUNT_MANAGER,
    ROLE_ACCOUNT_OWNER,
    ROLE_ACCOUNT_ADMINISTRATOR,
    ROLE_ORGANIZATION_OWNER,
    ROLE_ORGANIZATION_ADMINISTRATOR,
)

# A placeholder for a centralized permission definition.
# In a real application, this would likely be a more structured enum or class.
PERMISSIONS = {
    "FULL_ACCESS": ["*"],
    "ACCOUNT_MANAGEMENT": [
        "accounts.view",
        "accounts.edit",
        "organizations.view",
        "users.view",
    ],
    "ACCOUNT_OWNER": [
        "accounts.view",
        "accounts.edit",
        "organizations.create",
        "organizations.view",
        "organizations.edit",
        "organizations.delete",
        "users.invite",
        "users.view",
        "users.edit",
        "users.delete",
        "billing.view",
        "billing.manage",
    ],
    "ORGANIZATION_OWNER": [
        "organizations.view",
        "organizations.edit",
        "users.invite",
        "users.view",
        "users.edit",
        "users.delete",
        "subscriptions.view",
    ],
}


class Command(BaseCommand):
    help = "Initializes the database with immutable system and user roles."

    ROLES_TO_CREATE = [
        # 7.1.1 System Roles
        {
            "name": ROLE_SAAS_ADMINISTRATOR,
            "role_type": Role.RoleType.SYSTEM,
            "description": "Full platform access, can manage all organizations and users.",
            "permissions": PERMISSIONS["FULL_ACCESS"],
        },
        {
            "name": ROLE_SAAS_ACCOUNT_MANAGER,
            "role_type": Role.RoleType.SYSTEM,
            "description": "Can manage assigned accounts and their organizations.",
            "permissions": PERMISSIONS["ACCOUNT_MANAGEMENT"],
        },
        # 7.1.2 User Roles (Templates)
        {
            "name": ROLE_ACCOUNT_OWNER,
            "role_type": Role.RoleType.USER,
            "description": "Full access to account and all its organizations.",
            "permissions": PERMISSIONS["ACCOUNT_OWNER"],
        },
        {
            "name": ROLE_ACCOUNT_ADMINISTRATOR,
            "role_type": Role.RoleType.USER,
            "description": "Administrative access to account organizations.",
            "permissions": PERMISSIONS["ACCOUNT_OWNER"],  # Placeholder
        },
    ]

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Starting role initialization...")

        for role_data in self.ROLES_TO_CREATE:
            role, created = Role.objects.update_or_create(
                name=role_data["name"],
                organization__isnull=True,  # These are global/template roles
                role_type=role_data["role_type"],
                defaults={
                    "description": role_data["description"],
                    "permissions": role_data["permissions"],
                    "is_active": True,
                },
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Successfully created role: "{role.name}"'))
            else:
                self.stdout.write(f'Role "{role.name}" already exists, updated.')

        self.stdout.write(self.style.SUCCESS("Role initialization complete."))
