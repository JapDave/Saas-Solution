from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("agents", "0003_add_display_name_to_enabled_llm"),
        ("agents", "0003_add_tool_display_name_category"),
    ]

    operations = []
