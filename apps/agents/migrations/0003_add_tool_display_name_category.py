from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.db import migrations, models


def backfill_tool_display_fields(apps, schema_editor):
    OrganizationEnabledTool = apps.get_model("agents", "OrganizationEnabledTool")
    definitions_path = Path(settings.BASE_DIR) / "Business-Requirements" / "PRODUCT-MODULES" / "tools-list.json"
    tool_map = {}
    if definitions_path.exists():
        with definitions_path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        for entry in payload.get("tools", []):
            key = entry.get("toolKey")
            if key:
                tool_map[key] = {
                    "display_name": entry.get("displayName", key),
                    "category": entry.get("category", ""),
                }
    for record in OrganizationEnabledTool.objects.all():
        info = tool_map.get(record.tool_key, {})
        display_name = info.get("display_name") or record.display_name or record.tool_key
        category = info.get("category") or record.category or ""
        OrganizationEnabledTool.objects.filter(pk=record.pk).update(
            display_name=display_name,
            category=category,
        )


def noop(apps, schema_editor):
    return


class Migration(migrations.Migration):
    dependencies = [
        ("agents", "0002_add_disabled_by"),
    ]

    operations = [
        migrations.AddField(
            model_name="organizationenabledtool",
            name="display_name",
            field=models.CharField(default="", max_length=200, verbose_name="Display name"),
        ),
        migrations.AddField(
            model_name="organizationenabledtool",
            name="category",
            field=models.CharField(default="", max_length=50, verbose_name="Category"),
        ),
        migrations.RemoveConstraint(
            model_name="organizationenabledtool",
            name="uq_enabled_tool_per_org",
        ),
        migrations.AddConstraint(
            model_name="organizationenabledtool",
            constraint=models.UniqueConstraint(fields=("organization", "tool_key"), name="uq_enabled_tool_per_org"),
        ),
        migrations.RunPython(backfill_tool_display_fields, noop),
    ]
