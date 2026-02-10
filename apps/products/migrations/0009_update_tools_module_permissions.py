from django.db import migrations

MODULE_KEY = "TOOLS_MANAGEMENT"


def update_tools_permissions(apps, schema_editor):
    Module = apps.get_model("products", "Module")
    module = Module.objects.filter(key=MODULE_KEY).first()
    if not module:
        return
    module.exposed_permissions = [
        "tools:list",
        "tools:read",
        "tools:enable",
        "tools:disable",
        "tools:admin",
    ]
    module.save(update_fields=["exposed_permissions", "updated_at"])


def noop(apps, schema_editor):
    return


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0008_add_tools_module"),
    ]

    operations = [
        migrations.RunPython(update_tools_permissions, noop),
    ]
