from django.db import migrations

MODULE_KEY = "TOOLS_MANAGEMENT"


def create_tools_module(apps, schema_editor):
    Module = apps.get_model("products", "Module")
    Module.objects.update_or_create(
        key=MODULE_KEY,
        defaults={
            "code": "TOOL",
            "name": "Tools Management",
            "description": "Manage organization access to agent tools.",
            "subscribable": True,
            "configurable_attributes": {
                "tools_max_enabled_per_org": {"type": "int", "default": 50},
                "tools_invocations_per_month": {"type": "int", "default": 1000},
            },
            "exposed_permissions": [
                "tools:list",
                "tools:read",
                "tools:enable",
                "tools:disable",
                "tools:schema",
                "tools:admin",
            ],
        },
    )


def delete_tools_module(apps, schema_editor):
    Module = apps.get_model("products", "Module")
    Module.objects.filter(key=MODULE_KEY).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0007_add_llm_module"),
    ]

    operations = [
        migrations.RunPython(create_tools_module, delete_tools_module),
    ]

