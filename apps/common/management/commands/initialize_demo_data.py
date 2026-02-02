from __future__ import annotations

import os
from datetime import datetime, timedelta
from django.core import management
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import Account
from apps.organizations.models import Organization
from apps.users.models import User, Membership
from apps.roles.constants import ROLE_SAAS_ADMINISTRATOR, ROLE_AGENT_MANAGER
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
            email="demo-admin@hudhud.local",
            defaults={"full_name": "Demo SaaS Admin"},
        )
        admin_user.set_password(password)
        admin_user.is_active = True
        admin_user.save()

        manager_user, _ = User.objects.get_or_create(
            email="demo-manager@hudhud.local",
            defaults={"full_name": "Demo Agent Manager"},
        )
        manager_user.set_password(password)
        manager_user.is_active = True
        manager_user.save()

        member_user, _ = User.objects.get_or_create(
            email="demo-user@hudhud.local",
            defaults={"full_name": "Demo Member"},
        )
        member_user.set_password(password)
        member_user.is_active = True
        member_user.save()

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

        # 4) Role assignments
        sa_role, _ = Role.objects.get_or_create(name=ROLE_SAAS_ADMINISTRATOR)
        agent_mgr_role, _ = Role.objects.get_or_create(name=ROLE_AGENT_MANAGER)
        RoleAssignment.objects.get_or_create(user=admin_user, role=sa_role, organization=None)
        RoleAssignment.objects.get_or_create(user=manager_user, role=agent_mgr_role, organization=org)

        # 5) Memberships
        Membership.objects.get_or_create(user=admin_user, organization=org, defaults={"assigned_by": admin_user})
        Membership.objects.get_or_create(user=manager_user, organization=org, defaults={"assigned_by": admin_user})
        Membership.objects.get_or_create(user=member_user, organization=org, defaults={"assigned_by": admin_user})

        # 6) Products and Modules
        product, _ = Product.objects.get_or_create(
            key="HUDHUD_PLATFORM",
            defaults={"name": "Hudhud Platform", "description": "Demo product"},
        )
        llm_module, _ = Module.objects.get_or_create(
            key="LLM_MANAGEMENT",
            defaults={
                "code": "LLM",
                "name": "LLM Management",
                "description": "LLM discovery and enablement",
                "configurable_attributes": {"llms.max_enabled": 10},
                "exposed_permissions": [],
            },
        )
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

        self.stdout.write(self.style.SUCCESS("Demo data initialized. Users: demo-admin@, demo-manager@, demo-user@ (password: %s)" % password))
