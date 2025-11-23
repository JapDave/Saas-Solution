from django.db import migrations

MODULE_KEY = "CHANNELS_MANAGEMENT"


def create_module(apps, schema_editor):
    Module = apps.get_model("products", "Module")
    Module.objects.update_or_create(
        key=MODULE_KEY,
        defaults={
            "code": "CHAN",
            "name": "Channels Management",
            "description": "Configure web chat, WhatsApp, and X/Twitter channels.",
            "subscribable": True,
            "configurable_attributes": {
                "enabledChannelTypes": {
                    "web_chat": {"enabled": True, "maxInstances": 1},
                    "whatsapp": {"enabled": False, "maxInstances": 1},
                    "x": {"enabled": False, "maxInstances": 1},
                }
            },
            "exposed_permissions": [
                "channels:create",
                "channels:read",
                "channels:update",
                "channels:delete",
                "channels:activate",
                "channels:grants",
            ],
        },
    )


def delete_module(apps, schema_editor):
    Module = apps.get_model("products", "Module")
    Module.objects.filter(key=MODULE_KEY).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0002_add_agents_module"),
    ]

    operations = [
        migrations.RunPython(create_module, delete_module),
    ]

