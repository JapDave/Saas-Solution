from __future__ import annotations

import json

from django.db import migrations, models


def _wrap_system_prompts(apps, schema_editor):
    Agent = apps.get_model("agents", "Agent")
    AgentVersion = apps.get_model("agents", "AgentVersion")

    for model in (Agent, AgentVersion):
        for obj in model.objects.all():
            raw = getattr(obj, "system_prompts", None)
            if raw is None:
                new_value = json.dumps([])
            else:
                text = str(raw)
                candidate = text.strip()
                if candidate.startswith("[") and candidate.endswith("]"):
                    try:
                        parsed = json.loads(candidate)
                        if isinstance(parsed, list):
                            new_value = candidate
                        else:
                            new_value = json.dumps([text])
                    except Exception:
                        new_value = json.dumps([text])
                else:
                    new_value = json.dumps([text]) if text.strip() else json.dumps([])
            setattr(obj, "system_prompts", new_value)
            obj.save(update_fields=["system_prompts"])


class Migration(migrations.Migration):
    dependencies = [
        ("agents", "0004_merge_0003_llm_tool"),
    ]

    operations = [
        migrations.RunPython(_wrap_system_prompts, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="agent",
            name="system_prompts",
            field=models.JSONField(blank=True, default=list, verbose_name="System Prompts"),
        ),
        migrations.AlterField(
            model_name="agentversion",
            name="system_prompts",
            field=models.JSONField(default=list, verbose_name="System Prompts"),
        ),
    ]

