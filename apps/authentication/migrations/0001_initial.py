from django.db import migrations, models
from django.conf import settings
import uuid
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AuthSession",
            fields=[
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name="UUID")),
                ("is_active", models.BooleanField(db_index=True, default=True, verbose_name="Is active")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated at")),
                ("deleted_at", models.DateTimeField(blank=True, db_index=True, null=True, verbose_name="Deleted at")),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("access_jti", models.CharField(max_length=64, unique=True, verbose_name="Access token JTI")),
                ("refresh_jti", models.CharField(max_length=64, unique=True, verbose_name="Refresh token JTI")),
                ("access_expires_at", models.DateTimeField(verbose_name="Access token expires at")),
                ("refresh_expires_at", models.DateTimeField(verbose_name="Refresh token expires at")),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True, verbose_name="IP address")),
                ("user_agent", models.CharField(blank=True, default="", max_length=500, verbose_name="User agent")),
                ("last_activity_at", models.DateTimeField(auto_now_add=True, verbose_name="Last activity at")),
                ("deactivated_at", models.DateTimeField(blank=True, null=True, verbose_name="Deactivated at")),
                ("deactivated_reason", models.CharField(blank=True, default="", max_length=128, verbose_name="Deactivated reason")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="auth_sessions", to=settings.AUTH_USER_MODEL, verbose_name="User")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="authsession",
            index=models.Index(fields=["user_id", "created_at"], name="apps_authen_user_id_14f31c_idx"),
        ),
        migrations.AddIndex(
            model_name="authsession",
            index=models.Index(fields=["access_jti"], name="apps_authen_access__b84622_idx"),
        ),
        migrations.AddIndex(
            model_name="authsession",
            index=models.Index(fields=["refresh_jti"], name="apps_authen_refresh__c41954_idx"),
        ),
    ]
