#!/usr/bin/env bash
set -eu

host="${DB_HOST:-db}"
port="${DB_PORT:-5432}"

echo "Waiting for Postgres at ${host}:${port}..."
for _ in {1..60}; do
  if nc -z "${host}" "${port}" >/dev/null 2>&1; then
    echo "Postgres is up."
    break
  fi
  sleep 1
done

# Make migrations (usually dev-only; safe no-op if none)
python manage.py makemigrations accounts users organizations common products subscriptions roles teams files|| true

# Apply migrations
python manage.py migrate --noinput
python manage.py initialize_roles

# Create superuser only if env is provided
if [ -n "${DJANGO_SUPERUSER_EMAIL:-}" ]; then
  export DJANGO_SUPERUSER_PASSWORD="${DJANGO_SUPERUSER_PASSWORD:-admin123}"

  python <<'PY'
import os, sys, django
django.setup()
from django.contrib.auth import get_user_model

User = get_user_model()
email = os.environ["DJANGO_SUPERUSER_EMAIL"].strip()
password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "admin123")

try:
    if User.objects.filter(email__iexact=email).exists():
        print("Superuser already exists; nothing to do.")
    else:
        User.objects.create_superuser(email=email, password=password)
        print("Superuser created.")
except Exception as e:
    print(f"[ENTRYPOINT] Failed to create superuser {email}: {e}", file=sys.stderr)
    sys.exit(1)
PY
fi

# Collect static (no-op if none)
python manage.py collectstatic --noinput || true

# Run dev server if DEBUG=1, else gunicorn
if [ "${DEBUG:-0}" = "1" ]; then
  python manage.py runserver 0.0.0.0:8000
else
  gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120
fi

