from django.db import migrations, models
import hashlib
import uuid


def copy_jtis(apps, schema_editor):
    AuthSession = apps.get_model("authentication", "AuthSession")
    for session in AuthSession.objects.all():
        if not session.token_jti:
            if getattr(session, "access_jti", None):
                session.token_jti = session.access_jti
            else:
                session.token_jti = uuid.uuid4().hex
        if not session.refresh_token_hash:
            refresh_jti = getattr(session, "refresh_jti", "") or ""
            session.refresh_token_hash = hashlib.sha256(refresh_jti.encode("utf-8")).hexdigest() if refresh_jti else ""
        session.save(update_fields=["token_jti", "refresh_token_hash"])


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0004_alter_authsession_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="authsession",
            name="token_jti",
            field=models.CharField(max_length=64, null=True, blank=True),
        ),
        migrations.AddField(
            model_name="authsession",
            name="refresh_token_hash",
            field=models.CharField(max_length=128, null=True, blank=True),
        ),
        migrations.RunPython(code=copy_jtis, reverse_code=migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="authsession",
            name="access_jti",
        ),
        migrations.RemoveField(
            model_name="authsession",
            name="refresh_jti",
        ),
        migrations.AlterField(
            model_name="authsession",
            name="token_jti",
            field=models.CharField(max_length=64, unique=True),
        ),
        migrations.AlterField(
            model_name="authsession",
            name="refresh_token_hash",
            field=models.CharField(max_length=128),
        ),
        migrations.AddIndex(
            model_name="authsession",
            index=models.Index(fields=["token_jti"], name="ix_auth_token_jti"),
        ),
        migrations.AddIndex(
            model_name="authsession",
            index=models.Index(fields=["refresh_token_hash"], name="ix_auth_refresh_hash"),
        ),
    ]


def copy_jtis(apps, schema_editor):
    AuthSession = apps.get_model("authentication", "AuthSession")
    for session in AuthSession.objects.all():
        if not session.token_jti:
            if getattr(session, "access_jti", None):
                session.token_jti = session.access_jti
            else:
                session.token_jti = uuid.uuid4().hex
        if not session.refresh_token_hash:
            refresh_jti = getattr(session, "refresh_jti", "") or ""
            session.refresh_token_hash = hashlib.sha256(refresh_jti.encode("utf-8")).hexdigest() if refresh_jti else ""
        session.save(update_fields=["token_jti", "refresh_token_hash"])
