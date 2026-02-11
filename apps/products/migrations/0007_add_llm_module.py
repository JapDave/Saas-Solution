from django.db import migrations

MODULE_KEY = "LLM_MANAGEMENT"


def create_llm_module(apps, schema_editor):
    Module = apps.get_model("products", "Module")
    Module.objects.update_or_create(
        key=MODULE_KEY,
        defaults={
            "code": "LLM",
            "name": "LLM Management",
            "description": "Manage organization access to LLM models.",
            "subscribable": True,
            "configurable_attributes": {
                "llms.max_enabled": {"type": "int", "default": 20},
            },
            "exposed_permissions": [
                "llms:read",
                "llms:enable",
                "llms:disable",
                "llms:validate",
            ],
        },
    )


def delete_llm_module(apps, schema_editor):
    Module = apps.get_model("products", "Module")
    Module.objects.filter(key=MODULE_KEY).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0006_add_knowledge_base_module"),
    ]

    operations = [
        migrations.RunPython(create_llm_module, delete_llm_module),
    ]
