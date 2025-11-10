from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Dict, Iterable, List

from django.contrib.auth import get_user_model
from django.core.management import BaseCommand, CommandError, call_command
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Account
from apps.agents.models import Agent
from apps.agents.services import (
    enable_llm_for_organization,
    enable_tool_for_organization,
    save_agent_version,
)
from apps.agents.validators import validate_llm_configuration, validate_tools_configuration
from apps.organizations.models import Organization
from apps.products.models import Module
from apps.subscriptions.models import Subscription
from apps.teams.models import Team, TeamMember
from apps.users.models import UserOrganization

AGENTS_MODULE_KEY = "AGENTS_MANAGEMENT"


@dataclass
class SeedUser:
    email: str
    password: str
    full_name: str
    is_staff: bool = False
    is_superuser: bool = False


class Command(BaseCommand):
    help = "Populate the database with deterministic demo data spanning accounts, organizations, teams, and agents."

    DEMO_USERS: Dict[str, SeedUser] = {
        "superadmin": SeedUser(
            email="admin@hudhud.ai",
            password="Admin123!",
            full_name="HudHud Platform Admin",
            is_staff=True,
            is_superuser=True,
        ),
        "account_manager": SeedUser(
            email="manager@hudhud.ai",
            password="Manager123!",
            full_name="SaaS Account Manager",
            is_staff=True,
        ),
        "agent_manager": SeedUser(
            email="agent.manager@example.com",
            password="Agent123!",
            full_name="Acme Agent Manager",
        ),
        "viewer": SeedUser(
            email="viewer@example.com",
            password="Viewer123!",
            full_name="Org Read Only",
        ),
    }

    agent_permission_bundle: List[str] = [
        "agents:create",
        "agents:read",
        "agents:update",
        "agents:delete",
        "agents:versions:save",
        "agents:versions:switch",
        "agents:clone",
        "agents:llms:enable",
        "agents:tools:enable",
        "agents:admin",
    ]

    def add_arguments(self, parser):
        parser.add_argument(
            "--with-roles",
            action="store_true",
            help="Run the initialize_roles command before seeding (safe to rerun).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        with_roles = options.get("with_roles", False)
        if with_roles:
            call_command("initialize_roles", verbosity=0)

        module = Module.objects.filter(key=AGENTS_MODULE_KEY).first()
        if module is None:
            raise CommandError(
                "Module AGENTS_MANAGEMENT was not found. "
                "Run migrations (including products 0002) before seeding."
            )

        users = self._create_users()
        accounts = self._create_accounts(users)
        organizations = self._create_organizations(users, accounts)
        self._assign_memberships(users, organizations)
        self._create_subscriptions(module, organizations)
        self._create_teams(users, organizations)
        self._create_agents(users, organizations)

        self.stdout.write(self.style.SUCCESS("Demo data ready. Use the credentials below to explore the APIs:"))
        for key, seed in self.DEMO_USERS.items():
            self.stdout.write(f" - {seed.email} / {seed.password}  ({key.replace('_', ' ').title()})")

    # ------------------------------------------------------------------
    # Creation helpers
    # ------------------------------------------------------------------

    def _create_users(self) -> Dict[str, any]:
        User = get_user_model()
        results: Dict[str, any] = {}
        for label, seed in self.DEMO_USERS.items():
            defaults = {
                "full_name": seed.full_name,
                "is_staff": seed.is_staff,
                "is_superuser": seed.is_superuser,
                "is_active": True,
            }
            user, created = User.objects.update_or_create(email=seed.email, defaults=defaults)
            user.set_password(seed.password)
            user.save()
            results[label] = user
            action = "created" if created else "updated"
            self.stdout.write(self.style.SUCCESS(f"User {seed.email} {action}."))
        return results

    def _create_accounts(self, users: Dict[str, any]) -> Dict[str, Account]:
        admin = users["superadmin"]
        manager = users["account_manager"]
        return {
            "acme": self._upsert_account(
                name="Acme Holdings",
                contact_email="billing@acme.com",
                description="Enterprise account used for agent scenarios.",
                owner=admin,
            ),
            "globex": self._upsert_account(
                name="Globex Corporation",
                contact_email="ops@globex.com",
                description="Secondary account for negative/subscription testing.",
                owner=manager,
            ),
        }

    def _create_organizations(self, users, accounts) -> Dict[str, Organization]:
        admin = users["superadmin"]
        acme_org = self._upsert_org(
            account=accounts["acme"],
            name="Acme North America",
            description="Primary org for full agent lifecycle coverage.",
            owner=admin,
        )
        globex_org = self._upsert_org(
            account=accounts["globex"],
            name="Globex Research Lab",
            description="Org without the agents subscription for enforcement tests.",
            owner=users["account_manager"],
        )
        return {"acme": acme_org, "globex": globex_org}

    def _assign_memberships(self, users, organizations):
        admin = users["superadmin"]
        agent_manager = users["agent_manager"]
        viewer = users["viewer"]

        self._upsert_membership(
            user=agent_manager,
            organization=organizations["acme"],
            permission_keys=self.agent_permission_bundle,
            assigned_by=admin,
        )
        self._upsert_membership(
            user=viewer,
            organization=organizations["acme"],
            permission_keys=["agents:read"],
            assigned_by=admin,
        )

    def _create_subscriptions(self, module: Module, organizations):
        acme = organizations["acme"]
        now = timezone.now()
        config = {
            "agents_max_agents_per_org": 5,
            "agents_enabled_hosted_llms": ["gpt-4o-mini", "azure-gpt-35"],
            "agents_tool_invocations_per_month": 5000,
        }
        subscription, _ = Subscription.objects.update_or_create(
            organization=acme,
            module=module,
            defaults={
                "status": Subscription.Status.ACTIVE,
                "configuration": config,
                "start_date": now - timedelta(days=30),
                "end_date": None,
                "trial_end_date": now - timedelta(days=15),
            },
        )
        self.stdout.write(self.style.SUCCESS(f"Subscription for {acme.name} ensured (id={subscription.id})."))

    def _create_teams(self, users, organizations):
        admin = users["superadmin"]
        agent_manager = users["agent_manager"]
        viewer = users["viewer"]
        team, _ = Team.objects.get_or_create(
            organization=organizations["acme"],
            name="Acme Success Team",
            defaults={
                "description": "Handles onboarding and escalations.",
                "created_by": admin,
                "updated_by": admin,
            },
        )
        team.description = "Handles onboarding and escalations."
        team.updated_by = admin
        team.save()

        TeamMember.objects.update_or_create(
            team=team,
            user=agent_manager,
            defaults={"assigned_by": admin, "role_keys": ["owner"]},
        )
        TeamMember.objects.update_or_create(
            team=team,
            user=viewer,
            defaults={"assigned_by": admin, "role_keys": ["collaborator"]},
        )

    def _create_agents(self, users, organizations):
        agent_manager = users["agent_manager"]
        acme_org = organizations["acme"]

        enable_llm_for_organization(organization=acme_org, model_key="gpt-4o-mini", actor=agent_manager)
        enable_llm_for_organization(organization=acme_org, model_key="azure-gpt-35", actor=agent_manager)
        enable_tool_for_organization(organization=acme_org, tool_key="kb_retriever", actor=agent_manager)
        enable_tool_for_organization(organization=acme_org, tool_key="calculator", actor=agent_manager)

        agent, _ = Agent.objects.get_or_create(
            organization=acme_org,
            name="Customer Support Agent",
            defaults={
                "description": "Primary agent used for regression tests.",
                "system_prompts": "You are HudHud's tier-1 support agent. Be concise and friendly.",
                "llm_configuration": {},
                "tools_configuration": [],
                "created_by": agent_manager,
                "updated_by": agent_manager,
            },
        )
        agent.description = "Primary agent used for regression tests."
        agent.system_prompts = "You are HudHud's tier-1 support agent. Be concise and friendly."

        llm_payload = {
            "modelKey": "gpt-4o-mini",
            "modelProvider": "OpenAI",
            "configuration": {"temperature": 0.3, "maxTokens": 800, "topP": 0.9},
        }
        tools_payload = [
            {
                "toolKey": "kb_retriever",
                "configuration": {"collection_id": "demo-kb", "maxResults": 5, "similarityThreshold": 0.7},
            }
        ]
        agent.llm_configuration = validate_llm_configuration(llm_payload, organization=acme_org)
        agent.tools_configuration = validate_tools_configuration(tools_payload, organization=acme_org)
        agent.updated_by = agent_manager
        agent.save()

        if not agent.current_version:
            save_agent_version(agent, actor=agent_manager)

        draft_agent, _ = Agent.objects.get_or_create(
            organization=acme_org,
            name="Sales Research Agent",
            defaults={
                "description": "Draft agent without saved versions.",
                "system_prompts": "Assist sales with research tasks.",
                "llm_configuration": validate_llm_configuration(
                    {
                        "modelKey": "azure-gpt-35",
                        "modelProvider": "AzureOpenAI",
                        "configuration": {"temperature": 0.6, "maxTokens": 512},
                    },
                    organization=acme_org,
                ),
                "tools_configuration": validate_tools_configuration([], organization=acme_org),
                "created_by": agent_manager,
                "updated_by": agent_manager,
            },
        )
        draft_agent.updated_by = agent_manager
        draft_agent.save()

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    def _upsert_account(self, name: str, contact_email: str, description: str, owner) -> Account:
        account, created = Account.objects.get_or_create(
            name=name,
            defaults={
                "contact_email": contact_email,
                "description": description,
                "created_by": owner,
                "updated_by": owner,
            },
        )
        account.contact_email = contact_email
        account.description = description
        account.updated_by = owner
        if account.created_by_id is None:
            account.created_by = owner
        account.save()
        action = "created" if created else "updated"
        self.stdout.write(self.style.SUCCESS(f"Account '{name}' {action}."))
        return account

    def _upsert_org(self, account: Account, name: str, description: str, owner) -> Organization:
        organization, created = Organization.objects.get_or_create(
            account=account,
            name=name,
            defaults={
                "description": description,
                "created_by": owner,
                "updated_by": owner,
            },
        )
        organization.description = description
        organization.updated_by = owner
        if organization.created_by_id is None:
            organization.created_by = owner
        organization.save()
        action = "created" if created else "updated"
        self.stdout.write(self.style.SUCCESS(f"Organization '{name}' {action}."))
        return organization

    def _upsert_membership(self, user, organization, permission_keys: Iterable[str], assigned_by):
        keys = sorted({key.strip() for key in permission_keys if key})
        membership, created = UserOrganization.objects.update_or_create(
            user=user,
            organization=organization,
            defaults={
                "permission_keys": keys,
                "assigned_by": assigned_by,
                "is_active": True,
            },
        )
        action = "created" if created else "updated"
        self.stdout.write(
            self.style.SUCCESS(f"Membership for {user.email} in {organization.name} {action} with {len(keys)} permissions.")
        )
        return membership
