from django.db import migrations


MODULE_KEY = "AGENTS_MANAGEMENT"


def create_agents_module(apps, schema_editor):
    Module = apps.get_model("products", "Module")
    Module.objects.update_or_create(
        key=MODULE_KEY,
        defaults={
            "code": "AGNT",
            "name": "Agents Management",
            "description": "Create, configure, and manage AI agents with LLMs and tools.",
            "subscribable": True,
            "configurable_attributes": {
                "agents_max_agents_per_org": {"type": "int", "default": 10},
                "agents_enabled_hosted_llms": {"type": "array", "default": []},
                "agents_tool_invocations_per_month": {"type": "int", "default": 1000},
            },
            "exposed_permissions": [
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
            ],
        },
    )


def delete_agents_module(apps, schema_editor):
    Module = apps.get_model("products", "Module")
    Module.objects.filter(key=MODULE_KEY).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_agents_module, delete_agents_module),
    ]

