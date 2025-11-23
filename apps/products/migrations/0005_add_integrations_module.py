from django.db import migrations

MODULE_KEY = "INTEGRATIONS_MANAGEMENT"


def create_integrations_module(apps, schema_editor):
    Module = apps.get_model("products", "Module")
    Module.objects.update_or_create(
        key=MODULE_KEY,
        defaults={
            "code": "INTG",
            "name": "Integrations Management",
            "description": "Configure REST API and webhook integrations for external systems.",
            "subscribable": True,
            "configurable_attributes": {
                "integrations.api.enabled": {"type": "bool", "default": False},
                "integrations.api.maxInstances": {"type": "int", "default": 10},
                "integrations.api.maxInvocationsPerMonth": {"type": "int", "default": 10000},
                "integrations.webhook.enabled": {"type": "bool", "default": False},
                "integrations.webhook.maxInstances": {"type": "int", "default": 5},
                "integrations.webhook.maxInvocationsPerMonth": {"type": "int", "default": 5000},
            },
            "exposed_permissions": [
                "integrations:create",
                "integrations:read",
                "integrations:update",
                "integrations:activate",
                "integrations:deactivate",
                "integrations:delete",
                "integrations:test",
                "integrations:regenerate_secret",
            ],
        },
    )


def delete_integrations_module(apps, schema_editor):
    Module = apps.get_model("products", "Module")
    Module.objects.filter(key=MODULE_KEY).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0004_add_flows_module"),
    ]

    operations = [
        migrations.RunPython(create_integrations_module, delete_integrations_module),
    ]

