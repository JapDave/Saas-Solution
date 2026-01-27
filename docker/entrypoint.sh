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
GUNICORN_PORT="${GUNICORN_PORT:-8443}"
GUNICORN_WORKERS="${GUNICORN_WORKERS:-3}"

BASE_CMD=(
  gunicorn config.wsgi:application
  --bind "0.0.0.0:${GUNICORN_PORT}"
  --workers "${GUNICORN_WORKERS}"
  --timeout 120
  --certfile "${CERT_FILE}"
  --keyfile "${KEY_FILE}"
)

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

    echo "[ENTRYPOINT] APM_PROVIDER=OTEL -> opentelemetry-instrument (endpoint=${OTEL_EXPORTER_OTLP_ENDPOINT}, protocol=${OTEL_EXPORTER_OTLP_PROTOCOL}, service=${OTEL_SERVICE_NAME})"

    exec opentelemetry-instrument \
      --traces_exporter otlp \
      --metrics_exporter none \
      --service_name "${APM_SERVICE_NAME:-platform}" \
      "${BASE_CMD[@]}"
    ;;
  "DATADOG")
    exec ddtrace-run "${BASE_CMD[@]}"
    ;;
  *)
    exec "${BASE_CMD[@]}"
    ;;
esac
