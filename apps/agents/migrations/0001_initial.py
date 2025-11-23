#
# Generated manually for the Agents module.
#
import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("organizations", "0002_initial"),
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Agent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name="UUID")),
                ("is_active", models.BooleanField(db_index=True, default=True, verbose_name="Is active")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated at")),
                ("deleted_at", models.DateTimeField(blank=True, db_index=True, null=True, verbose_name="Deleted at")),
                ("name", models.CharField(max_length=250, verbose_name="Name")),
                ("description", models.CharField(blank=True, default="", max_length=250, verbose_name="Description")),
                ("system_prompts", models.TextField(blank=True, default="", verbose_name="System Prompts")),
                ("llm_configuration", models.JSONField(blank=True, default=dict, verbose_name="LLM configuration")),
                ("tools_configuration", models.JSONField(blank=True, default=list, verbose_name="Tools configuration")),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("active", "Active"),
                            ("archived", "Archived"),
                            ("deleted", "Deleted"),
                        ],
                        default="draft",
                        max_length=20,
                        verbose_name="State",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="agents_created",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Created by",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="agents",
                        to="organizations.organization",
                        verbose_name="Organization",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="agents_updated",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Updated by",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["organization", "name"], name="ix_agent_org_name"),
                    models.Index(fields=["state"], name="ix_agent_state"),
                ],
            },
        ),
        migrations.CreateModel(
            name="AgentVersion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name="UUID")),
                ("is_active", models.BooleanField(db_index=True, default=True, verbose_name="Is active")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated at")),
                ("deleted_at", models.DateTimeField(blank=True, db_index=True, null=True, verbose_name="Deleted at")),
                ("version_number", models.PositiveIntegerField(verbose_name="Version number")),
                ("name", models.CharField(max_length=250, verbose_name="Name")),
                ("description", models.CharField(blank=True, default="", max_length=250, verbose_name="Description")),
                ("system_prompts", models.TextField(verbose_name="System Prompts")),
                ("llm_configuration", models.JSONField(verbose_name="LLM configuration")),
                ("tools_configuration", models.JSONField(blank=True, default=list, verbose_name="Tools configuration")),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="agent_versions_created",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Created by",
                    ),
                ),
                (
                    "agent",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="versions",
                        to="agents.agent",
                        verbose_name="Agent",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="OrganizationEnabledTool",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name="UUID")),
                ("is_active", models.BooleanField(db_index=True, default=True, verbose_name="Is active")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated at")),
                ("deleted_at", models.DateTimeField(blank=True, db_index=True, null=True, verbose_name="Deleted at")),
                ("tool_key", models.CharField(max_length=100, verbose_name="Tool key")),
                ("enabled_at", models.DateTimeField(auto_now_add=True, verbose_name="Enabled at")),
                ("disabled_at", models.DateTimeField(blank=True, null=True, verbose_name="Disabled at")),
                (
                    "enabled_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="enabled_tools",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Enabled by",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="enabled_tools",
                        to="organizations.organization",
                        verbose_name="Organization",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="OrganizationEnabledLLM",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name="UUID")),
                ("is_active", models.BooleanField(db_index=True, default=True, verbose_name="Is active")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated at")),
                ("deleted_at", models.DateTimeField(blank=True, db_index=True, null=True, verbose_name="Deleted at")),
                ("model_key", models.CharField(max_length=100, verbose_name="Model key")),
                ("model_provider", models.CharField(max_length=100, verbose_name="Model provider")),
                ("enabled_at", models.DateTimeField(auto_now_add=True, verbose_name="Enabled at")),
                ("disabled_at", models.DateTimeField(blank=True, null=True, verbose_name="Disabled at")),
                (
                    "enabled_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="enabled_llms",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Enabled by",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="enabled_llms",
                        to="organizations.organization",
                        verbose_name="Organization",
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="agent",
            name="current_version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="active_agents",
                to="agents.agentversion",
                verbose_name="Current version",
            ),
        ),
        migrations.AddConstraint(
            model_name="organizationenabledtool",
            constraint=models.UniqueConstraint(
                condition=models.Q(("disabled_at__isnull", True)),
                fields=("organization", "tool_key"),
                name="uq_enabled_tool_per_org",
            ),
        ),
        migrations.AddConstraint(
            model_name="organizationenabledllm",
            constraint=models.UniqueConstraint(
                condition=models.Q(("disabled_at__isnull", True)),
                fields=("organization", "model_key"),
                name="uq_enabled_llm_per_org",
            ),
        ),
        migrations.AddConstraint(
            model_name="agentversion",
            constraint=models.UniqueConstraint(fields=("agent", "version_number"), name="uq_agent_version_seq"),
        ),
        migrations.AddConstraint(
            model_name="agent",
            constraint=models.UniqueConstraint(
                condition=models.Q(("deleted_at__isnull", True)),
                fields=("organization", "name"),
                name="uq_agent_name_per_org",
            ),
        ),
    ]

