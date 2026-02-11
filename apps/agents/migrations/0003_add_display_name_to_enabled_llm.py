from django.db import migrations, models


def backfill_display_name(apps, schema_editor):
    OrganizationEnabledLLM = apps.get_model("agents", "OrganizationEnabledLLM")
    LLMDefinition = apps.get_model("llms", "LLMDefinition")
    definitions = {
        row.model_key: row.display_name
        for row in LLMDefinition.objects.all().only("model_key", "display_name")
    }
    for record in OrganizationEnabledLLM.objects.all():
        if record.display_name:
            continue
        display = definitions.get(record.model_key, "") or ""
        record.display_name = display
        record.save(update_fields=["display_name"])


def clear_display_name(apps, schema_editor):
    OrganizationEnabledLLM = apps.get_model("agents", "OrganizationEnabledLLM")
    OrganizationEnabledLLM.objects.update(display_name="")


class Migration(migrations.Migration):
    dependencies = [
        ("agents", "0002_add_disabled_by"),
        ("llms", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="organizationenabledllm",
            name="display_name",
            field=models.CharField(blank=True, default="", max_length=200, verbose_name="Display name"),
        ),
        migrations.RunPython(backfill_display_name, clear_display_name),
    ]
