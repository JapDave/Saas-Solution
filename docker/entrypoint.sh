#!/usr/bin/env bash
set -e

host="${DB_HOST:-db}"
port="${DB_PORT:-5432}"

echo "Waiting for Postgres at $host:$port..."
for i in {1..60}; do nc -z "$host" "$port" && break || sleep 1; done

python manage.py migrate --noinput || true
python manage.py makemigrations --noinput || true
python manage.py migrate --noinput

# collect static for admin/Swagger assets
python manage.py collectstatic --noinput

if [ "${AUTO_CREATE_SUPERUSER:-0}" = "1" ]; then
python - <<'PY'
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE","config.settings")
django.setup()
from django.contrib.auth import get_user_model
User = get_user_model()
u, created = User.objects.get_or_create(
    username=os.environ.get("DJANGO_SUPERUSER_USERNAME","admin"),
    defaults={"email": os.environ.get("DJANGO_SUPERUSER_EMAIL","admin@example.com"),
              "is_staff": True, "is_superuser": True, "full_name": "Super Admin"}
)
pwd = os.environ.get("DJANGO_SUPERUSER_PASSWORD","admin123")
if created:
    u.set_password(pwd); u.save(); print("Superuser created.")
else:
    print("Superuser exists.")
PY
fi

gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3
