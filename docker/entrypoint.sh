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
python manage.py makemigrations --noinput || true

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

# Build gunicorn command with TLS
CERT_FILE="${CERT_FILE:-certs/hudhud.local.pem}"
KEY_FILE="${KEY_FILE:-certs/hudhud.local-key.pem}"
GUNICORN_PORT="${GUNICORN_PORT:-8000}"
GUNICORN_TLS_PORT="${GUNICORN_TLS_PORT:-9443}"
GUNICORN_WORKERS="${GUNICORN_WORKERS:-3}"
MANAGE_SSL_DIRECTLY="$(echo "${MANAGE_SSL_DIRECTLY:-false}" | tr '[:upper:]' '[:lower:]')"
SECURED_PLATFORM="$(echo "${secured_platform:-${SECURED_PLATFORM:-true}}" | tr '[:upper:]' '[:lower:]')"

# Build gunicorn command with optional TLS (direct mode)
BASE_CMD=(
  gunicorn config.wsgi:application
  --workers "${GUNICORN_WORKERS}"
  --timeout 120
)

if [ "${MANAGE_SSL_DIRECTLY}" = "true" ] && [ "${SECURED_PLATFORM}" = "true" ] && [ -f "${CERT_FILE}" ] && [ -f "${KEY_FILE}" ]; then
  BASE_CMD+=(--bind "0.0.0.0:${GUNICORN_TLS_PORT}" --certfile "${CERT_FILE}" --keyfile "${KEY_FILE}")
else
  BASE_CMD+=(--bind "0.0.0.0:${GUNICORN_PORT}")
fi

APM_PROVIDER="$(echo "${APM_PROVIDER:-}" | tr -d '\r' | tr '[:lower:]' '[:upper:]')"

case "${APM_PROVIDER}" in
  "OTEL")
    # Map APM_* variables to standard OTEL_* envs if not already set
    export OTEL_SERVICE_NAME="${OTEL_SERVICE_NAME:-${APM_SERVICE_NAME:-platform}}"
    export OTEL_RESOURCE_ATTRIBUTES="${OTEL_RESOURCE_ATTRIBUTES:-service.namespace=${APM_SERVICE_NAMESPACE:-hudhud},deployment.environment=${APM_ENVIRONMENT:-local}}"
    export OTEL_EXPORTER_OTLP_ENDPOINT="${OTEL_EXPORTER_OTLP_ENDPOINT:-${APM_OTEL_EXPORTER_OTLP_ENDPOINT:-http://otel-collector:4317}}"
    export OTEL_EXPORTER_OTLP_PROTOCOL="${OTEL_EXPORTER_OTLP_PROTOCOL:-${APM_OTEL_EXPORTER_OTLP_PROTOCOL:-grpc}}"
    export OTEL_EXPORTER_OTLP_INSECURE="${OTEL_EXPORTER_OTLP_INSECURE:-${APM_OTEL_EXPORTER_OTLP_INSECURE:-true}}"
    export OTEL_TRACES_EXPORTER="${OTEL_TRACES_EXPORTER:-otlp}"
    export OTEL_METRICS_EXPORTER="${OTEL_METRICS_EXPORTER:-none}"
    export OTEL_LOG_LEVEL="${OTEL_LOG_LEVEL:-info}"
    # Disable noisy auto-instrumentations; rely on custom middleware + manual OTEL init in settings.
    # export OTEL_PYTHON_DISABLED_INSTRUMENTATIONS="${OTEL_PYTHON_DISABLED_INSTRUMENTATIONS:-requests,urllib3}"

    echo "[ENTRYPOINT] APM_PROVIDER=OTEL -> native OTLP export (endpoint=${OTEL_EXPORTER_OTLP_ENDPOINT}, protocol=${OTEL_EXPORTER_OTLP_PROTOCOL}, service=${OTEL_SERVICE_NAME})"

    exec "${BASE_CMD[@]}"
    ;;
  "DATADOG")
    exec ddtrace-run "${BASE_CMD[@]}"
    ;;
  *)
    exec "${BASE_CMD[@]}"
    ;;
esac
