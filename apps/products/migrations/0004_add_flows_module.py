from django.db import migrations

MODULE_KEY = "FLOWS_MANAGEMENT"


def create_flows_module(apps, schema_editor):
    Module = apps.get_model("products", "Module")
    Module.objects.update_or_create(
        key=MODULE_KEY,
        defaults={
            "code": "FLOW",
            "name": "Flows Management",
            "description": (
                "Design, version, and manage workflow automations with optimistic locking "
                "and state transitions."
            ),
            "subscribable": True,
            "configurable_attributes": {
                "flows_max_flows_per_org": {
                    "type": "int",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 10000,
                    "description": "Maximum number of flows allowed per organization.",
                },
            },
            "exposed_permissions": [
                "agents:flows:create",
                "agents:flows:read",
                "agents:flows:update",
                "agents:flows:delete",
                "agents:flows:publish",
                "agents:flows:disable",
                "agents:flows:enable",
                "agents:flows:clone",
                "agents:flows:versions:read",
            ],
        },
    )


def delete_flows_module(apps, schema_editor):
    Module = apps.get_model("products", "Module")
    Module.objects.filter(key=MODULE_KEY).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0003_add_channels_module"),
    ]

    operations = [
        migrations.RunPython(create_flows_module, delete_flows_module),
    ]

