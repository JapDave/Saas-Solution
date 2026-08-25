from __future__ import annotations

import os
from datetime import datetime, timedelta
from django.core import management
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import Account
from apps.organizations.models import Organization
from apps.users.models import User, UserOrganization
from apps.roles.constants import (
    ROLE_SAAS_ADMINISTRATOR,
    ROLE_SAAS_ACCOUNT_MANAGER,
    ROLE_AGENT_MANAGER,
    ROLE_ACCOUNT_OWNER,
    ROLE_ACCOUNT_ADMINISTRATOR,
    ROLE_ORGANIZATION_OWNER,
    ROLE_ORGANIZATION_ADMINISTRATOR,
    LLM_PERMISSION_KEYS,
)
from apps.roles.models import Role, RoleAssignment
from apps.products.models import Product, Module
from apps.subscriptions.models import Subscription
from apps.agents.services import enable_llm_for_organization
from apps.agents.definitions import get_llm_definition


class Command(BaseCommand):
    help = "Seed demo data across accounts/orgs/users/roles/subscriptions (debug-friendly)."

    def add_arguments(self, parser):
        parser.add_argument("--debug-only", action="store_true", help="Only run when DEBUG is True")
        parser.add_argument("--force", action="store_true", help="Force run even if DEBUG is False")
        parser.add_argument("--password", type=str, default=None, help="Password to set for demo users")
        parser.add_argument("--llm-fixture", type=str, default="apps/llms/fixtures/llms_debug_seed.json", help="LLM fixture path to seed before enabling")

    def handle(self, *args, **opts):
        from django.conf import settings

        if opts["debug_only"] and not settings.DEBUG and not opts["force"]:
            self.stdout.write(self.style.WARNING("Skipped: DEBUG-only and DEBUG is False. Use --force to override."))
            return

        password = opts["password"] or os.environ.get("DEMO_PASSWORD") or "Admin123!"

        # 1) Ensure LLM definitions are seeded (debug fixture by default)
        management.call_command(
            "initialize_llms",
            path=opts["llm_fixture"],
            truncate=False,
            verbosity=0,
        )

        # 2) Create demo users
        admin_user, _ = User.objects.get_or_create(
            email="demo-admin@saas-platform.local",
            defaults={"full_name": "Demo SaaS Admin"},
        )
        admin_user.set_password(password)
        admin_user.is_active = True
        admin_user.save()

        manager_user, _ = User.objects.get_or_create(
            email="demo-manager@saas-platform.local",
            defaults={"full_name": "Demo Agent Manager"},
        )
        manager_user.set_password(password)
        manager_user.is_active = True
        manager_user.save()

        member_user, _ = User.objects.get_or_create(
            email="demo-user@saas-platform.local",
            defaults={"full_name": "Demo Member"},
        )
        member_user.set_password(password)
        member_user.is_active = True
        member_user.save()

        saas_manager_user, _ = User.objects.get_or_create(
            email="demo-saas-manager@saas-platform.local",
            defaults={"full_name": "Demo SaaS Account Manager"},
        )
        saas_manager_user.set_password(password)
        saas_manager_user.is_active = True
        saas_manager_user.save()

        account_owner_user, _ = User.objects.get_or_create(
            email="demo-account-owner@saas-platform.local",
            defaults={"full_name": "Demo Account Owner"},
        )
        account_owner_user.set_password(password)
        account_owner_user.is_active = True
        account_owner_user.save()

        account_admin_user, _ = User.objects.get_or_create(
            email="demo-account-admin@saas-platform.local",
            defaults={"full_name": "Demo Account Admin"},
        )
        account_admin_user.set_password(password)
        account_admin_user.is_active = True
        account_admin_user.save()

        org_owner_user, _ = User.objects.get_or_create(
            email="demo-org-owner@saas-platform.local",
            defaults={"full_name": "Demo Org Owner"},
        )
        org_owner_user.set_password(password)
        org_owner_user.is_active = True
        org_owner_user.save()

        org_admin_user, _ = User.objects.get_or_create(
            email="demo-org-admin@saas-platform.local",
            defaults={"full_name": "Demo Org Admin"},
        )
        org_admin_user.set_password(password)
        org_admin_user.is_active = True
        org_admin_user.save()

        custom_role_user, _ = User.objects.get_or_create(
            email="demo-custom-role@saas-platform.local",
            defaults={"full_name": "Demo Custom Role"},
        )
        custom_role_user.set_password(password)
        custom_role_user.is_active = True
        custom_role_user.save()

        # 3) Account and Organization
        account, _ = Account.objects.get_or_create(
            name="Demo Account",
            defaults={"contact_email": "account@demo.local", "created_by": admin_user},
        )
        org, _ = Organization.objects.get_or_create(
            account=account,
            name="Demo Org",
            defaults={"description": "Demo organization", "created_by": admin_user},
        )

        owner_account, _ = Account.objects.get_or_create(
            name="Owner Account",
            defaults={"contact_email": "owner@demo.local", "created_by": account_owner_user},
        )
        owner_org, _ = Organization.objects.get_or_create(
            account=owner_account,
            name="Owner Org",
            defaults={"description": "Org created by org owner", "created_by": org_owner_user},
        )

        no_sub_account, _ = Account.objects.get_or_create(
            name="No Sub Account",
            defaults={"contact_email": "nosub@demo.local", "created_by": admin_user},
        )
        no_sub_org, _ = Organization.objects.get_or_create(
            account=no_sub_account,
            name="No Sub Org",
            defaults={"description": "Org without LLM subscription", "created_by": admin_user},
        )

        # 4) Role assignments
        sa_role, _ = Role.objects.get_or_create(name=ROLE_SAAS_ADMINISTRATOR)
        saas_mgr_role, _ = Role.objects.get_or_create(name=ROLE_SAAS_ACCOUNT_MANAGER)
        agent_mgr_role, _ = Role.objects.get_or_create(name=ROLE_AGENT_MANAGER, organization=org, defaults={
            "description": "Org-scoped Agent Manager role for demo",
            "permissions": [],
            "role_type": Role.RoleType.USER_CUSTOM,
            "created_by": admin_user,
        })
        acct_owner_role, _ = Role.objects.get_or_create(name=ROLE_ACCOUNT_OWNER, organization=org, defaults={
            "description": "Org-scoped Account Owner role for demo",
            "permissions": [],
            "role_type": Role.RoleType.USER_CUSTOM,
            "created_by": admin_user,
        })
        acct_admin_role, _ = Role.objects.get_or_create(name=ROLE_ACCOUNT_ADMINISTRATOR, organization=org, defaults={
            "description": "Org-scoped Account Admin role for demo",
            "permissions": [],
            "role_type": Role.RoleType.USER_CUSTOM,
            "created_by": admin_user,
        })
        org_owner_role, _ = Role.objects.get_or_create(name=ROLE_ORGANIZATION_OWNER, organization=org, defaults={
            "description": "Org-scoped Org Owner role for demo",
            "permissions": [],
            "role_type": Role.RoleType.USER_CUSTOM,
            "created_by": admin_user,
        })
        org_admin_role, _ = Role.objects.get_or_create(name=ROLE_ORGANIZATION_ADMINISTRATOR, organization=org, defaults={
            "description": "Org-scoped Org Admin role for demo",
            "permissions": [],
            "role_type": Role.RoleType.USER_CUSTOM,
            "created_by": admin_user,
        })
        custom_role, _ = Role.objects.get_or_create(name="LLM Custom Role", organization=org, defaults={
            "description": "Custom role with LLM permissions",
            "permissions": list(LLM_PERMISSION_KEYS),
            "role_type": Role.RoleType.USER_CUSTOM,
            "created_by": admin_user,
        })
        RoleAssignment.objects.get_or_create(user=admin_user, role=sa_role, organization=None)
        RoleAssignment.objects.get_or_create(user=saas_manager_user, role=saas_mgr_role, organization=None)
        RoleAssignment.objects.get_or_create(user=manager_user, role=agent_mgr_role, organization=org)
        RoleAssignment.objects.get_or_create(user=account_owner_user, role=acct_owner_role, organization=org)
        RoleAssignment.objects.get_or_create(user=account_admin_user, role=acct_admin_role, organization=org)
        RoleAssignment.objects.get_or_create(user=org_owner_user, role=org_owner_role, organization=org)
        RoleAssignment.objects.get_or_create(user=org_admin_user, role=org_admin_role, organization=org)
        RoleAssignment.objects.get_or_create(user=custom_role_user, role=custom_role, organization=org)

        # 5) Memberships
        UserOrganization.objects.get_or_create(user=admin_user, organization=org, defaults={"assigned_by": admin_user})
        UserOrganization.objects.get_or_create(user=manager_user, organization=org, defaults={"assigned_by": admin_user})
        UserOrganization.objects.get_or_create(user=member_user, organization=org, defaults={"assigned_by": admin_user})
        UserOrganization.objects.get_or_create(user=custom_role_user, organization=org, defaults={"assigned_by": admin_user})

        # 6) Products and Modules
        product, _ = Product.objects.get_or_create(
            key="SAAS_PLATFORM",
            defaults={"name": "SaaS Platform", "description": "Demo product"},
        )
        llm_module, _ = Module.objects.get_or_create(
            key="LLM_MANAGEMENT",
            defaults={
                "code": "LLM",
                "name": "LLM Management",
                "description": "LLM discovery and enablement",
                "configurable_attributes": {"llms.max_enabled": 10},
                "exposed_permissions": list(LLM_PERMISSION_KEYS),
            },
        )
        if not llm_module.exposed_permissions:
            llm_module.exposed_permissions = list(LLM_PERMISSION_KEYS)
            llm_module.save(update_fields=["exposed_permissions", "updated_at"])
        agents_module, _ = Module.objects.get_or_create(
            key="AGENTS_MANAGEMENT",
            defaults={
                "code": "AGT",
                "name": "Agents Management",
                "description": "Agent runtime and config",
                "configurable_attributes": {"agents_enabled_hosted_llms": ["deepseek-r1-debug"]},
                "exposed_permissions": [],
            },
        )
        llm_module.products.add(product)
        agents_module.products.add(product)

        # 7) Subscriptions
        start = timezone.now()
        defaults_sub = {
            "status": Subscription.Status.ACTIVE,
            "start_date": start,
            "end_date": start + timedelta(days=365),
            "trial_end_date": None,
        }
        Subscription.objects.get_or_create(
            organization=org,
            module=llm_module,
            defaults={**defaults_sub, "configuration": {"llms.max_enabled": 10}},
        )
        Subscription.objects.get_or_create(
            organization=org,
            module=agents_module,
            defaults={**defaults_sub, "configuration": {"agents_enabled_hosted_llms": ["deepseek-r1-debug"]}},
        )

        # 8) Enable one LLM for the org (if definition exists)
        debug_llm_key = "gpt-4o-mini-debug"
        if get_llm_definition(debug_llm_key):
            enable_llm_for_organization(organization=org, model_key=debug_llm_key, actor=admin_user)

        # Assign SaaS Account Manager to the demo account for scoped access (preferences fallback)
        saas_manager_user.user_preferences = {
            **(saas_manager_user.user_preferences or {}),
            "assigned_account_ids": [account.id],
        }
        saas_manager_user.save(update_fields=["user_preferences", "updated_at"])

        self.stdout.write(
            self.style.SUCCESS(
                "LLM demo data initialized. Users: demo-admin@, demo-manager@, demo-user@, "
                "demo-saas-manager@, demo-account-owner@, demo-account-admin@, demo-org-owner@, "
                "demo-org-admin@, demo-custom-role@ (password: %s)" % password
            )
        )
