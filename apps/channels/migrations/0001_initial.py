import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("organizations", "0002_initial"),
        ("teams", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Channel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name="UUID")),
                ("is_active", models.BooleanField(db_index=True, default=True, verbose_name="Is active")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated at")),
                ("deleted_at", models.DateTimeField(blank=True, db_index=True, null=True, verbose_name="Deleted at")),
                ("channel_type", models.CharField(choices=[("web_chat", "Web Chat"), ("whatsapp", "WhatsApp"), ("x", "X / Twitter")], max_length=20, verbose_name="Channel Type")),
                ("name", models.CharField(max_length=500, verbose_name="Name")),
                ("description", models.CharField(blank=True, default="", max_length=500, verbose_name="Description")),
                ("state", models.CharField(choices=[("inactive", "Inactive"), ("active", "Active"), ("deleted", "Deleted")], default="inactive", max_length=20, verbose_name="State")),
                ("configurations", models.JSONField(default=dict, verbose_name="Configurations")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="channels_created", to=settings.AUTH_USER_MODEL, verbose_name="Created by")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="channels", to="organizations.organization", verbose_name="Organization")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="channels_updated", to=settings.AUTH_USER_MODEL, verbose_name="Updated by")),
            ],
        ),
        migrations.CreateModel(
            name="ChannelAccessGrant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name="UUID")),
                ("is_active", models.BooleanField(db_index=True, default=True, verbose_name="Is active")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated at")),
                ("deleted_at", models.DateTimeField(blank=True, db_index=True, null=True, verbose_name="Deleted at")),
                ("subject_type", models.CharField(choices=[("user", "User"), ("team", "Team")], max_length=10, verbose_name="Subject type")),
                ("permissions", django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=50), blank=True, default=list, size=None, verbose_name="Permissions")),
                ("granted_at", models.DateTimeField(auto_now_add=True, verbose_name="Granted at")),
                ("revoked_at", models.DateTimeField(blank=True, null=True, verbose_name="Revoked at")),
                ("channel", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="grants", to="channels.channel", verbose_name="Channel")),
                ("granted_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="channel_grants_made", to=settings.AUTH_USER_MODEL, verbose_name="Granted by")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="channel_grants", to="organizations.organization", verbose_name="Organization")),
                ("subject_team", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="channel_grants", to="teams.team")),
                ("subject_user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="channel_grants", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddIndex(
            model_name="channel",
            index=models.Index(fields=["organization", "channel_type"], name="ix_channel_org_type"),
        ),
        migrations.AddConstraint(
            model_name="channel",
            constraint=models.UniqueConstraint(condition=models.Q(("deleted_at__isnull", True)), fields=("organization", "name"), name="uq_channel_name_per_org"),
        ),
        migrations.AddIndex(
            model_name="channelaccessgrant",
            index=models.Index(fields=["channel", "subject_type"], name="ix_channel_grant_subject"),
        ),
    ]
