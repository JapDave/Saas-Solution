from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("agents", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="organizationenabledllm",
            name="disabled_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="disabled_llms",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Disabled by",
            ),
        ),
        migrations.AddField(
            model_name="organizationenabledtool",
            name="disabled_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="disabled_tools",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Disabled by",
            ),
        ),
    ]

