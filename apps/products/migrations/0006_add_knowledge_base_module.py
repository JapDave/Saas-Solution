from django.db import migrations

MODULE_KEY = "KNOWLEDGE_BASE_MANAGEMENT"


def create_kb_module(apps, schema_editor):
    Module = apps.get_model("products", "Module")
    Module.objects.update_or_create(
        key=MODULE_KEY,
        defaults={
            "code": "KB",
            "name": "Knowledge Base Management",
            "description": "Organize knowledge collections and resources.",
            "subscribable": True,
            "configurable_attributes": {
                "kb.collections.max": {"type": "int", "default": 3},
                "kb.resources_per_collection": {"type": "int", "default": 10},
            },
            "exposed_permissions": [
                "kb:collections:create",
                "kb:collections:read",
                "kb:collections:update",
                "kb:collections:delete",
                "kb:collections:archive",
                "kb:collections:restore",
                "kb:resources:create",
                "kb:resources:delete",
                "kb:resources:move",
                "kb:resources:copy",
            ],
        },
    )


def delete_kb_module(apps, schema_editor):
    Module = apps.get_model("products", "Module")
    Module.objects.filter(key=MODULE_KEY).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0005_add_integrations_module"),
    ]

    operations = [
        migrations.RunPython(create_kb_module, delete_kb_module),
    ]

