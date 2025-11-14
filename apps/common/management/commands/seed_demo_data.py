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
from apps.channels.models import Channel
from apps.channels.validators import validate_channel_configuration
from apps.flows.models import Flow, FlowVersion
from apps.flows.services import (
    create_draft_from_published,
    create_flow,
    publish_flow,
    disable_flow,
)
from apps.integrations.models import Integration
from apps.organizations.models import Organization
from apps.roles.constants import AGENT_PERMISSION_KEYS, CHANNEL_PERMISSION_KEYS, FLOW_PERMISSION_KEYS, INTEGRATION_PERMISSION_KEYS
from apps.products.models import Module
from apps.subscriptions.models import Subscription
from apps.teams.models import Team, TeamMember
from apps.users.models import UserOrganization

AGENTS_MODULE_KEY = "AGENTS_MANAGEMENT"
CHANNELS_MODULE_KEY = "CHANNELS_MANAGEMENT"
FLOWS_MODULE_KEY = "FLOWS_MANAGEMENT"
INTEGRATIONS_MODULE_KEY = "INTEGRATIONS_MANAGEMENT"


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

    agent_permission_bundle: List[str] = list(AGENT_PERMISSION_KEYS)
    channel_permission_bundle: List[str] = list(CHANNEL_PERMISSION_KEYS)
    flow_permission_bundle: List[str] = list(FLOW_PERMISSION_KEYS)
    integration_permission_bundle: List[str] = list(INTEGRATION_PERMISSION_KEYS)

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

        agents_module = Module.objects.filter(key=AGENTS_MODULE_KEY).first()
        if agents_module is None:
            raise CommandError(
                "Module AGENTS_MANAGEMENT was not found. "
                "Run migrations (including products 0002) before seeding."
            )
        channels_module = Module.objects.filter(key=CHANNELS_MODULE_KEY).first()
        if channels_module is None:
            raise CommandError(
                "Module CHANNELS_MANAGEMENT was not found. "
                "Run migrations (including products 0003) before seeding."
            )
        flows_module = Module.objects.filter(key=FLOWS_MODULE_KEY).first()
        if flows_module is None:
            raise CommandError(
                "Module FLOWS_MANAGEMENT was not found. "
                "Run migrations (including products 0004) before seeding."
            )
        integrations_module = Module.objects.filter(key=INTEGRATIONS_MODULE_KEY).first()
        if integrations_module is None:
            raise CommandError(
                "Module INTEGRATIONS_MANAGEMENT was not found. "
                "Run migrations (including products 0005) before seeding."
            )

        users = self._create_users()
        accounts = self._create_accounts(users)
        organizations = self._create_organizations(users, accounts)
        self._assign_memberships(users, organizations)
        self._create_subscriptions(agents_module, channels_module, flows_module, integrations_module, organizations)
        self._create_teams(users, organizations)
        self._create_agents(users, organizations)
        self._create_channels(users, organizations)
        self._create_flows(users, organizations)
        self._create_integrations(users, organizations)

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
            permission_keys=self.agent_permission_bundle
            + self.channel_permission_bundle
            + self.flow_permission_bundle
            + self.integration_permission_bundle,
            assigned_by=admin,
        )
        self._upsert_membership(
            user=viewer,
            organization=organizations["acme"],
            permission_keys=["agents:read", "channels:read", "agents:flows:read"],
            assigned_by=admin,
        )

    def _create_subscriptions(
        self,
        agents_module: Module,
        channels_module: Module,
        flows_module: Module,
        integrations_module: Module,
        organizations,
    ):
        acme = organizations["acme"]
        now = timezone.now()
        config = {
            "agents_max_agents_per_org": 5,
            "agents_enabled_hosted_llms": ["gpt-4o-mini", "azure-gpt-35"],
            "agents_tool_invocations_per_month": 5000,
        }
        subscription, _ = Subscription.objects.update_or_create(
            organization=acme,
            module=agents_module,
            defaults={
                "status": Subscription.Status.ACTIVE,
                "configuration": config,
                "start_date": now - timedelta(days=30),
                "end_date": None,
                "trial_end_date": now - timedelta(days=15),
            },
        )
        self.stdout.write(self.style.SUCCESS(f"Subscription for {acme.name} ensured (id={subscription.id})."))

        channel_config = {
            "enabledChannelTypes": {
                "web_chat": {"enabled": True, "maxInstances": 3},
                "whatsapp": {"enabled": True, "maxInstances": 1},
                "x": {"enabled": False, "maxInstances": 1},
            }
        }
        channel_sub, _ = Subscription.objects.update_or_create(
            organization=acme,
            module=channels_module,
            defaults={
                "status": Subscription.Status.ACTIVE,
                "configuration": channel_config,
                "start_date": now - timedelta(days=30),
                "end_date": None,
                "trial_end_date": now - timedelta(days=15),
            },
        )
        self.stdout.write(
            self.style.SUCCESS(f"Channel subscription for {acme.name} ensured (id={channel_sub.id}).")
        )

        flow_config = {
            "flows_max_flows_per_org": 12,
        }
        flow_sub, _ = Subscription.objects.update_or_create(
            organization=acme,
            module=flows_module,
            defaults={
                "status": Subscription.Status.ACTIVE,
                "configuration": flow_config,
                "start_date": now - timedelta(days=30),
                "end_date": None,
                "trial_end_date": now - timedelta(days=15),
            },
        )
        self.stdout.write(
            self.style.SUCCESS(f"Flows subscription for {acme.name} ensured (id={flow_sub.id}).")
        )

        integrations_config = {
            "integrations.api": {"enabled": True, "maxInstances": 5, "maxInvocationsPerMonth": 5000},
            "integrations.webhook": {"enabled": True, "maxInstances": 3, "maxInvocationsPerMonth": 2500},
        }
        integration_sub, _ = Subscription.objects.update_or_create(
            organization=acme,
            module=integrations_module,
            defaults={
                "status": Subscription.Status.ACTIVE,
                "configuration": integrations_config,
                "start_date": now - timedelta(days=30),
                "end_date": None,
                "trial_end_date": now - timedelta(days=15),
            },
        )
        self.stdout.write(
            self.style.SUCCESS(f"Integrations subscription for {acme.name} ensured (id={integration_sub.id}).")
        )

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

    def _create_channels(self, users, organizations):
        agent_manager = users["agent_manager"]
        acme_org = organizations["acme"]

        config = validate_channel_configuration(
            "web_chat",
            {
                "webChatDisplayName": "Acme Support Chat",
                "webChatPosition": "right",
                "webChatDirection": "rtl",
                "webChatTheme": "standard",
                "webChatSupportedLanguages": ["ar", "en"],
                "webChatDefaultLanguage": "ar",
                "webChatSize": 1,
                "webChatTitleText": "Welcome to Acme Support",
                "webChatAllowRenderingMedia": True,
                "webChatAllowSendingMedia": False,
                "webChatAllowNavMainMenu": False,
                "webChatAllowNavPreviousMenu": False,
                "webChatSessionDuration": 600,
            },
        )
        channel, created = Channel.objects.update_or_create(
            organization=acme_org,
            name="Acme Web Chat",
            defaults={
                "channel_type": "web_chat",
                "configurations": config,
                "created_by": agent_manager,
                "updated_by": agent_manager,
            },
        )
        action = "created" if created else "updated"
        self.stdout.write(self.style.SUCCESS(f"Channel '{channel.name}' {action}."))

    def _create_flows(self, users, organizations):
        agent_manager = users["agent_manager"]
        acme_org = organizations["acme"]

        flow_name = "Customer Onboarding Flow"
        flow_description = "Guides new customers through a welcome email and Slack notification."
        flow_configs = {"autoRetry": True, "timezone": "UTC"}
        flow_json = {
            "nodes": [
                {
                    "id": "trigger-signup",
                    "type": "trigger",
                    "position": {"x": 50, "y": 50},
                    "data": {
                        "triggerType": "webhook",
                        "eventType": "customer.signup",
                        "webhookId": "signup-trigger",
                    },
                },
                {
                    "id": "action-email",
                    "type": "action",
                    "position": {"x": 320, "y": 40},
                    "data": {
                        "actionType": "send_email",
                        "templateKey": "welcome-email",
                        "subject": "Welcome to Acme!",
                    },
                },
                {
                    "id": "action-slack",
                    "type": "action",
                    "position": {"x": 320, "y": 160},
                    "data": {
                        "actionType": "slack_notify",
                        "channel": "#new-signups",
                        "message": "A new customer just signed up.",
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "trigger-signup", "target": "action-email"},
                {"id": "e2", "source": "trigger-signup", "target": "action-slack"},
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1.0},
        }

        flow = Flow.all_objects.filter(organization=acme_org, name=flow_name).first()
        if flow:
            flow.description = flow_description
            flow.flow_configurations = flow_configs
            flow.updated_by = agent_manager
            flow.save(update_fields=["description", "flow_configurations", "updated_by", "updated_at"])
            self.stdout.write(self.style.SUCCESS(f"Flow '{flow_name}' updated."))
        else:
            flow = create_flow(
                organization=acme_org,
                name=flow_name,
                description=flow_description,
                flow_configurations=flow_configs,
                flow_json=flow_json,
                actor=agent_manager,
            )
            self.stdout.write(self.style.SUCCESS(f"Flow '{flow_name}' created."))

        if not flow.versions.filter(state=FlowVersion.FlowVersionState.PUBLISHED, is_active=True).exists():
            publish_flow(flow, actor=agent_manager)
            self.stdout.write(self.style.SUCCESS("Flow published."))

        if flow.versions.count() < 2:
            create_draft_from_published(flow, actor=agent_manager)
            self.stdout.write(self.style.SUCCESS("Draft version created for flow."))

        disabled_flow = create_flow(
            organization=acme_org,
            name="Escalation Workflow",
            description="Escalates stalled tickets to leadership.",
            flow_configurations={"autoRetry": False, "timezone": "UTC"},
            flow_json={
                "nodes": [
                    {
                        "id": "trigger-escalation",
                        "type": "trigger",
                        "position": {"x": 0, "y": 0},
                        "data": {"triggerType": "webhook", "eventType": "ticket.escalated"},
                    },
                    {
                        "id": "action-notify",
                        "type": "action",
                        "position": {"x": 300, "y": 80},
                        "data": {"actionType": "send_email", "templateKey": "escalation-alert"},
                    },
                ],
                "edges": [{"id": "edge-escalation", "source": "trigger-escalation", "target": "action-notify"}],
                "viewport": {"x": 0, "y": 0, "zoom": 1.0},
            },
            actor=agent_manager,
        )
        publish_flow(disabled_flow, actor=agent_manager)
        disable_flow(disabled_flow, actor=agent_manager)
        self.stdout.write(self.style.SUCCESS("Escalation flow seeded and disabled to cover state transitions."))

    def _create_integrations(self, users, organizations):
        agent_manager = users["agent_manager"]
        acme_org = organizations["acme"]

        api_integration, created = Integration.objects.update_or_create(
            organization=acme_org,
            name="CRM Customer Lookup",
            defaults={
                "integration_type": Integration.IntegrationType.API,
                "description": "Fetches customer data from CRM.",
                "url": "https://api.crm.example.com/customers/{customerId}",
                "method": "GET",
                "headers": [{"key": "Authorization", "value": "Bearer demo-token"}],
                "parameters": [
                    {"key": "customerId", "name": "Customer ID", "type": "path", "required": True, "description": "CRM ID"},
                ],
                "request_body": "",
                "response_mappings": [
                    {"key": "customerName", "name": "Customer Name", "jsonPath": "$.data.name"},
                    {"key": "customerEmail", "name": "Customer Email", "jsonPath": "$.data.email"},
                ],
                "created_by": agent_manager,
                "updated_by": agent_manager,
            },
        )
        api_integration.full_clean()
        api_integration.save()
        api_integration.increment_invocations(15)
        self.stdout.write(
            self.style.SUCCESS(f"Integration '{api_integration.name}' {'created' if created else 'updated'}.")
        )

        webhook, created = Integration.objects.update_or_create(
            organization=acme_org,
            name="Order Notifications",
            defaults={
                "integration_type": Integration.IntegrationType.WEBHOOK,
                "description": "Receives order events from commerce platform.",
                "response_mappings": [
                    {"key": "orderId", "name": "Order ID", "jsonPath": "$.order.id"},
                    {"key": "orderTotal", "name": "Order Total", "jsonPath": "$.order.total"},
                ],
                "webhook_sample_payload": {"order": {"id": "ORDER-123", "total": 199}},
                "created_by": agent_manager,
                "updated_by": agent_manager,
            },
        )
        webhook.regenerate_webhook_credentials()
        webhook.full_clean()
        webhook.save()
        webhook.increment_invocations(8)
        self.stdout.write(
            self.style.SUCCESS(f"Webhook integration '{webhook.name}' {'created' if created else 'updated'}.")
        )

        reporting_api, created = Integration.objects.update_or_create(
            organization=acme_org,
            name="Analytics Export",
            defaults={
                "integration_type": Integration.IntegrationType.API,
                "description": "Exports analytics data weekly.",
                "url": "https://analytics.example.com/export/{reportId}",
                "method": "POST",
                "headers": [{"key": "Content-Type", "value": "application/json"}],
                "parameters": [
                    {"key": "reportId", "name": "Report ID", "type": "path", "required": True, "description": ""},
                    {"key": "email", "name": "Email", "type": "query", "required": False, "description": ""},
                ],
                "request_body": '{"range": "{dateRange}"}',
                "response_mappings": [{"key": "status", "name": "Status", "jsonPath": "$.status"}],
                "created_by": agent_manager,
                "updated_by": agent_manager,
            },
        )
        reporting_api.full_clean()
        reporting_api.state = Integration.IntegrationState.INACTIVE
        reporting_api.is_active = False
        reporting_api.save()
        self.stdout.write(
            self.style.SUCCESS(f"Integration '{reporting_api.name}' {'created' if created else 'updated'} and set inactive.")
        )

        archived_webhook, created = Integration.objects.update_or_create(
            organization=acme_org,
            name="Legacy Warehouse Hook",
            defaults={
                "integration_type": Integration.IntegrationType.WEBHOOK,
                "description": "Deprecated hook kept for reference.",
                "response_mappings": [{"key": "warehouseId", "name": "Warehouse ID", "jsonPath": "$.warehouse.id"}],
                "webhook_sample_payload": {"warehouse": {"id": "WH-1"}},
                "created_by": agent_manager,
                "updated_by": agent_manager,
            },
        )
        archived_webhook.regenerate_webhook_credentials()
        archived_webhook.full_clean()
        archived_webhook.save()
        archived_webhook.mark_deleted()
        self.stdout.write(
            self.style.SUCCESS(
                f"Webhook integration '{archived_webhook.name}' {'created' if created else 'updated'} and marked deleted."
            )
        )

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
