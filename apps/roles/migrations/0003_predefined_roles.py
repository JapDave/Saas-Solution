from django.db import migrations

SECURITY_ROLES = [
    ("Security Admin", ["manage_security", "view_audit_logs", "manage_sessions"]),
    ("Session Manager", ["view_sessions", "revoke_sessions"]),
]


def seed_roles(apps, schema_editor):
    Role = apps.get_model("roles", "Role")
    for name, perms in SECURITY_ROLES:
        Role.objects.get_or_create(
            organization=None,
            name=name,
            defaults={
                "permissions": perms,
                "role_type": "system",
                "is_active": True,
                "created_by_id": None,
            },
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("roles", "0002_initial"),
    ]

    operations = [
        migrations.RunPython(seed_roles, reverse_code=noop),
    ]
