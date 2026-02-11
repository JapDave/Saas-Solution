from django.db import migrations

MODULE_KEY = "LLM_MANAGEMENT"


def add_llm_list_permission(apps, schema_editor):
    Module = apps.get_model("products", "Module")
    module = Module.objects.filter(key=MODULE_KEY).first()
    if not module:
        return
    perms = list(module.exposed_permissions or [])
    if "llms:list" not in perms:
        perms.append("llms:list")
        module.exposed_permissions = perms
        module.save(update_fields=["exposed_permissions", "updated_at"])


def remove_llm_list_permission(apps, schema_editor):
    Module = apps.get_model("products", "Module")
    module = Module.objects.filter(key=MODULE_KEY).first()
    if not module:
        return
    perms = [p for p in (module.exposed_permissions or []) if p != "llms:list"]
    module.exposed_permissions = perms
    module.save(update_fields=["exposed_permissions", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0008_add_tools_module"),
    ]

    operations = [
        migrations.RunPython(add_llm_list_permission, remove_llm_list_permission),
    ]
