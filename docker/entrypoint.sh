#!/usr/bin/env bash
set -euo pipefail

host="${DB_HOST:-db}"
port="${DB_PORT:-5432}"

echo "Waiting for Postgres at ${host}:${port}..."
for i in {1..60}; do
  nc -z "${host}" "${port}" && break || sleep 1
done

python manage.py migrate --noinput

# Create superuser if requested (idempotent)
if [ "${DJANGO_SUPERUSER_USERNAME:-}" ]; then
python <<'PY'
import os
import django
django.setup()
from django.contrib.auth import get_user_model
User = get_user_model()
username = os.environ["DJANGO_SUPERUSER_USERNAME"]
email = os.environ.get("DJANGO_SUPERUSER_EMAIL","admin@example.com")
password = os.environ.get("DJANGO_SUPERUSER_PASSWORD","admin123")
u, created = User.objects.get_or_create(username=username, defaults={"email": email, "is_staff": True, "is_superuser": True})
if created:
    u.set_password(password); u.save(); print("Superuser created.")
else:
    print("Superuser exists.")
PY
fi

# Collect static (safe even in dev; no-op if none)
python manage.py collectstatic --noinput || true

# Run dev server if DEBUG=1, else gunicorn
if [ "${DEBUG:-0}" = "1" ]; then
  python manage.py runserver 0.0.0.0:8000
else
  gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120
fi
