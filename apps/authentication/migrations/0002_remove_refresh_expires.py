from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql='ALTER TABLE "authentication_authsession" DROP COLUMN IF EXISTS "refresh_expires_at";',
                    reverse_sql='ALTER TABLE "authentication_authsession" ADD COLUMN "refresh_expires_at" timestamp with time zone;',
                ),
            ],
            state_operations=[],
        )
    ]
