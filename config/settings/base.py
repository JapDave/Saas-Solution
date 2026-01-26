import os
import ssl
from pathlib import Path
from datetime import timedelta
from typing import Iterable
from urllib.parse import urlparse

from dotenv import load_dotenv

_DEFAULT_SSL_VERSION = getattr(ssl, "PROTOCOL_TLS_SERVER", ssl.PROTOCOL_TLS)

def _wrap_socket_compat(
    socket,
    certfile=None,
    keyfile=None,
    server_side=False,
    ssl_version=None,
    cert_reqs=None,
    **kwargs,
):
    context = ssl.SSLContext(ssl_version or _DEFAULT_SSL_VERSION)
    if certfile:
        context.load_cert_chain(certfile, keyfile)
    if cert_reqs is not None:
        context.verify_mode = cert_reqs
    return context.wrap_socket(socket, server_side=server_side, **kwargs)

if not hasattr(ssl, "wrap_socket"):
    ssl.wrap_socket = _wrap_socket_compat

BASE_DIR = Path(__file__).resolve().parents[2]  # …/hudhud_backend
load_dotenv(BASE_DIR / ".env")

# -------------------------------------------------------------------
# Environment resolution helpers (ENVIRONMENT-BASELINE.md)
# -------------------------------------------------------------------
def _truthy(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _detect_provider() -> str:
    if os.getenv("GOOGLE_CLOUD_PROJECT"):
        return "GCP"
    if all(os.getenv(key) for key in ("AWS_DEFAULT_REGION", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_ENV")):
        return "AWS"
    return "ON_PREM"


_DEPLOYMENT_PROVIDER = _detect_provider()


def _get_secret_from_gcp(key: str) -> str | None:
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project:
        return None
    try:
        from google.cloud import secretmanager  # type: ignore
    except Exception as exc:
        raise RuntimeError("GCP secret manager client not available.") from exc
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project}/secrets/{key}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("utf-8")


def _get_secret_from_aws(key: str) -> str | None:
    env = os.getenv("AWS_ENV")
    if not env:
        return None
    try:
        import boto3  # type: ignore
    except Exception as exc:
        raise RuntimeError("AWS boto3 client not available.") from exc
    ssm = boto3.client("ssm")
    name = f"/platform/{env}/{key}"
    response = ssm.get_parameter(Name=name, WithDecryption=True)
    return response["Parameter"]["Value"]


def _get_config(
    key: str,
    *,
    default: str | None = None,
    required: bool = False,
    env_aliases: Iterable[str] = (),
) -> str | None:
    for env_key in (*env_aliases, key):
        value = os.getenv(env_key)
        if value not in (None, ""):
            return value

    value = None
    try:
        if _DEPLOYMENT_PROVIDER == "GCP":
            value = _get_secret_from_gcp(key)
        elif _DEPLOYMENT_PROVIDER == "AWS":
            value = _get_secret_from_aws(key)
    except Exception:
        if required:
            raise
        value = None

    if value not in (None, ""):
        return value
    if required:
        raise RuntimeError(f"Missing required configuration value: {key}")
    return default

# -------------------------------------------------------------------
# Core switches
# -------------------------------------------------------------------
DEBUG = _truthy(os.getenv("DEBUG", "0"))
SECRET_KEY = _get_config("secret_key_platform", required=True, env_aliases=("SECRET_KEY",)) or "change-me-in-prod"

STAGING = _truthy(_get_config("STAGING", default="True"))
DEVELOPMENT_SERVER = _truthy(_get_config("DEVELOPMENT_SERVER", default="false"))

CORE_URL = _get_config("CORE_URL", required=True)
ALTERNATIVE_CORE_URL = _get_config("ALTERNATIVE_CORE_URL", default=CORE_URL)
INTERNAL_CORE_URL = _get_config("INTERNAL_CORE_URL", default=CORE_URL)
CORE_TOKEN = _get_config("CORE_TOKEN", required=True)
CRON_TOKEN = _get_config("CRON_TOKEN", required=True)
DEFAULT_WEBSOCKET_TYPE = _get_config("DEFAULT_WEBSOCKET_TYPE", default="socketio")
WEBSOCKET_URL = _get_config("WEBSOCKET_URL", default="")

PLATFORM_URL = _get_config("Platform_URL", required=True, env_aliases=("PLATFORM_URL",))
EXTRA_PLATFORM_DOMAINS = _split_csv(_get_config("extra_platform_domains", default=""))
SECURED_PLATFORM = _truthy(_get_config("secured_platform", default="True"))
APPEND_HOST_PORT = _get_config("APPEND_HOST_PORT", default="")
MANAGE_SSL_DIRECTLY = _truthy(_get_config("MANAGE_SSL_DIRECTLY", default="false"))


def _with_port(host: str) -> str:
    if APPEND_HOST_PORT and ":" not in host:
        return f"{host}:{APPEND_HOST_PORT}"
    return host


def _origin_from_url(url: str | None) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return url


_platform_hosts = [host for host in ([PLATFORM_URL] + EXTRA_PLATFORM_DOMAINS) if host]
_platform_hosts_with_port = [_with_port(host) for host in _platform_hosts]
_allowed_hosts = set(_split_csv(os.getenv("ALLOWED_HOSTS", "")))
_allowed_hosts.update(_platform_hosts)
ALLOWED_HOSTS = sorted(h for h in _allowed_hosts if h) or ["*"]

# -------------------------------------------------------------------
# Applications
# -------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]
THIRD_PARTY_APPS = [
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "corsheaders",
]
LOCAL_APPS = [
    "apps.users",
    "apps.common.apps.CommonConfig",
    "apps.accounts",
    "apps.organizations",
    "apps.teams",
    "apps.products",
    "apps.subscriptions",
    "apps.roles",
    "apps.files",
    "apps.agents",
    "apps.channels",
    "apps.flows",
    "apps.integrations",
    "apps.knowledge_base",
    "apps.llms",
    "apps.tools",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

AUTH_USER_MODEL = "users.User"

# -------------------------------------------------------------------
# APM & logging baseline
# -------------------------------------------------------------------
DJANGO_LOG_LEVEL = os.getenv("DJANGO_LOG_LEVEL", "INFO")
ENABLE_APM = _truthy(_get_config("ENABLE_APM", default="False"))
APM_PROVIDER = (_get_config("APM_PROVIDER") or "").upper() if ENABLE_APM else ""
APM_SERVICE_NAME = _get_config("APM_SERVICE_NAME", default="platform")
APM_ENVIRONMENT = _get_config("APM_ENVIRONMENT", default="staging")
APM_VERSION = _get_config("APM_VERSION", default=None)
APM_SERVICE_NAMESPACE = _get_config("APM_SERVICE_NAMESPACE", default="hudhud")
ENABLE_OTEL_LOGS_EXPORTER = _truthy(_get_config("ENABLE_OTEL_LOGS_EXPORTER", default="False"))

if ENABLE_APM:
    allowed_providers = {"ELASTIC", "DATADOG", "GCP", "OTEL", "DYANATRACE"}
    if APM_PROVIDER not in allowed_providers:
        raise RuntimeError("APM_PROVIDER must be set to one of: ELASTIC, DATADOG, GCP, OTEL, DYANATRACE")
    provider_requirements = {
        "ELASTIC": ("ELASTIC_APM_SERVER_URL", "ELASTIC_APM_SECRET_TOKEN"),
        "DATADOG": ("DATADOG_TRACE_AGENT_HOST", "DATADOG_TRACE_AGENT_PORT"),
        "OTEL": ("APM_OTEL_EXPORTER_OTLP_ENDPOINT",),
    }
    for key in provider_requirements.get(APM_PROVIDER, ()):
        if not _get_config(key):
            raise RuntimeError(f"Missing required APM configuration: {key}")
    if APM_PROVIDER != "OTEL" and ENABLE_OTEL_LOGS_EXPORTER:
        raise RuntimeError("ENABLE_OTEL_LOGS_EXPORTER can only be true when APM_PROVIDER=OTEL")

ELASTIC_APM_SERVER_URL = _get_config("ELASTIC_APM_SERVER_URL", default="")
ELASTIC_APM_SECRET_TOKEN = _get_config("ELASTIC_APM_SECRET_TOKEN", default="")
ELASTIC_APM_TRANSACTION_SAMPLE_RATE = _get_config("ELASTIC_APM_TRANSACTION_SAMPLE_RATE", default="")
ELASTIC_APM_CAPTURE_HEADERS = _get_config("ELASTIC_APM_CAPTURE_HEADERS", default="")

DATADOG_TRACE_AGENT_HOST = _get_config("DATADOG_TRACE_AGENT_HOST", default="")
DATADOG_TRACE_AGENT_PORT = _get_config("DATADOG_TRACE_AGENT_PORT", default="")
DD_TRACE_ENABLED = _get_config("DD_TRACE_ENABLED", default="")
DD_LOGS_INJECTION = _get_config("DD_LOGS_INJECTION", default="")
DD_TRACE_SAMPLE_RATE = _get_config("DD_TRACE_SAMPLE_RATE", default="")

APM_OTEL_EXPORTER_OTLP_ENDPOINT = _get_config("APM_OTEL_EXPORTER_OTLP_ENDPOINT", default="")
APM_OTEL_SAMPLE_RATE = _get_config("APM_OTEL_SAMPLE_RATE", default="")

GOOGLE_APPLICATION_CREDENTIALS = _get_config("GOOGLE_APPLICATION_CREDENTIALS", default="")


# -------------------------------------------------------------------
# Audit logging baseline
# -------------------------------------------------------------------
AUDIT_LOG_SENSITIVE_FIELDS = _split_csv(os.getenv("AUDIT_LOG_SENSITIVE_FIELDS", ""))
AUDIT_TRACKED_MODELS = os.getenv("AUDIT_TRACKED_MODELS", "*").strip()
AUDIT_EXCLUDED_MODELS = _split_csv(
    os.getenv("AUDIT_EXCLUDED_MODELS", "common.AuditLog,common.DataChangeLog")
)
AUDIT_SYSTEM_USER_EMAIL = _get_config("AUDIT_SYSTEM_USER_EMAIL", default="")

# -------------------------------------------------------------------
# Login security & SSO
# -------------------------------------------------------------------
ALLOWED_SESSIONS_PER_USER = int(_get_config("ALLOWED_SESSIONS_PER_USER", default="0") or 0)
ALLOWED_LOGIN_ATTEMPTS = int(_get_config("ALLOWED_LOGIN_ATTEMPTS", default="3") or 3)
LOGIN_ATTEMPTS_TIME_WINDOW = int(_get_config("LOGIN_ATTEMPTS_TIME_WINDOW", default="10") or 10)
PASSWORD_MIN_SMALL_LETTERS = int(_get_config("PASSWORD_MIN_SMALL_LETTERS", default="1") or 1)
PASSWORD_MIN_CAPITAL_LETTERS = int(_get_config("PASSWORD_MIN_CAPITAL_LETTERS", default="1") or 1)
PASSWORD_MIN_NUMBERS = int(_get_config("PASSWORD_MIN_NUMBERS", default="1") or 1)
PASSWORD_MIN_SPECIAL_CHARACTERS = int(_get_config("PASSWORD_MIN_SPECIAL_CHARACTERS", default="1") or 1)

SSO_ENABLED = _truthy(_get_config("SSO_ENABLED", default="False"))
OIDC_RP_CLIENT_ID = _get_config("OIDC_RP_CLIENT_ID", default="")
OIDC_RP_CLIENT_SECRET = _get_config("OIDC_RP_CLIENT_SECRET", default="")
OIDC_OP_AUTHORIZATION_ENDPOINT = _get_config("OIDC_OP_AUTHORIZATION_ENDPOINT", default="")
OIDC_OP_TOKEN_ENDPOINT = _get_config("OIDC_OP_TOKEN_ENDPOINT", default="")
OIDC_OP_USER_ENDPOINT = _get_config("OIDC_OP_USER_ENDPOINT", default="")
OIDC_OP_JWKS_ENDPOINT = _get_config("OIDC_OP_JWKS_ENDPOINT", default="")
OIDC_RP_SCOPES = _get_config("OIDC_RP_SCOPES", default="")

if SSO_ENABLED:
    required_oidc = {
        "OIDC_RP_CLIENT_ID": OIDC_RP_CLIENT_ID,
        "OIDC_RP_CLIENT_SECRET": OIDC_RP_CLIENT_SECRET,
        "OIDC_OP_AUTHORIZATION_ENDPOINT": OIDC_OP_AUTHORIZATION_ENDPOINT,
        "OIDC_OP_TOKEN_ENDPOINT": OIDC_OP_TOKEN_ENDPOINT,
        "OIDC_OP_JWKS_ENDPOINT": OIDC_OP_JWKS_ENDPOINT,
    }
    missing = [key for key, value in required_oidc.items() if not value]
    if missing:
        raise RuntimeError(f"Missing required OIDC configuration: {', '.join(missing)}")

# -------------------------------------------------------------------
# Middleware (order matters)
# -------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.common.middlewares.security.CSPMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # static in prod-ish
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "apps.common.middlewares.audit.AuditLogMiddleware",
]

if ENABLE_APM:
    _auth_index = MIDDLEWARE.index("django.contrib.auth.middleware.AuthenticationMiddleware") + 1
    MIDDLEWARE.insert(_auth_index, "apps.common.middlewares.apm.APMContextMiddleware")

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# -------------------------------------------------------------------
# Database
# -------------------------------------------------------------------
DB_NAME = _get_config("DB_NAME", required=True)
DB_USER = _get_config(
    "DB_USERNAME_PLATFORM",
    required=True,
    env_aliases=("DB_USER", "DB_USERNAME"),
)
DB_PASSWORD = _get_config(
    "DB_PASSWORD_PLATFORM",
    required=True,
    env_aliases=("DB_PASSWORD",),
)
DB_HOST = _get_config("DB_host", required=True, env_aliases=("DB_HOST",))
DB_PORT = _get_config("DB_PORT", default="5432")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": DB_NAME,
        "USER": DB_USER,
        "PASSWORD": DB_PASSWORD,
        "HOST": DB_HOST,
        "PORT": DB_PORT,
        "CONN_MAX_AGE": 60,
        "ATOMIC_REQUESTS": True,
        "OPTIONS": {"connect_timeout": 5},
    }
}

# ------------------------------------------------------------------------------
# TEMPLATES
# ------------------------------------------------------------------------------

# https://docs.djangoproject.com/en/dev/ref/settings/#templates
TEMPLATES = [
    {
        # https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-TEMPLATES-BACKEND
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # https://docs.djangoproject.com/en/dev/ref/settings/#dirs
        "DIRS": [],
        # https://docs.djangoproject.com/en/dev/ref/settings/#app-dirs
        "APP_DIRS": True,
        "OPTIONS": {
            # https://docs.djangoproject.com/en/dev/ref/settings/#template-context-processors
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.i18n",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.template.context_processors.tz",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# -------------------------------------------------------------------
# REST / Auth / OpenAPI
# -------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework_simplejwt.authentication.JWTAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.common.exception_handler.exception_handler",
    "DEFAULT_PAGINATION_CLASS": "apps.common.paginations.StandardPagination",
    "DEFAULT_THROTTLE_CLASSES": ["apps.common.throttling.DynamicScopedRateThrottle"],
    "PAGE_SIZE": 10,
    # allow ?page_size=... in requests (used by the test)
    "PAGE_SIZE_QUERY_PARAM": "page_size",
    # optional: cap max
    "MAX_PAGE_SIZE": 100,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Huhud Rest Api Backend",
    "DESCRIPTION": "Accounts/Orgs/Users/Teams/Subscriptions",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # Use our standardized error envelope as the default error schema
    "COMPONENT_SPLIT_REQUEST": True,
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
}

# -------------------------------------------------------------------
# DRF standardized error
# -------------------------------------------------------------------
DRF_STANDARDIZED_ERRORS = {
    "EXCEPTION_FORMATTER_CLASS": "apps.common.exceptions.CustomExceptionFormatter",
}

# -------------------------------------------------------------------
# Static / Media / Storages
# -------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# -------------------------------------------------------------------
# Storage (MINIO baseline)
# -------------------------------------------------------------------
STORAGE_TYPE = _get_config("storage_type", default="LOCAL_STORAGE")
MINIO_ACCESS_KEY_ID = _get_config("MINIO_ACCESS_KEY_ID")
MINIO_SECRET_ACCESS_KEY = _get_config("MINIO_SECRET_ACCESS_KEY")
MINIO_STORAGE_BUCKET_NAME = _get_config("MINIO_STORAGE_BUCKET_NAME")
MINIO_CUSTOM_DOMAIN = _get_config("MINIO_CUSTOM_DOMAIN")
MINIO_STORAGE_USE_HTTPS = _truthy(_get_config("MINIO_STORAGE_USE_HTTPS", default="True"))
MINIO_STORAGE_VERIFY_HTTPS = _truthy(_get_config("MINIO_STORAGE_VERIFY_HTTPS", default="true"))
MINIO_STORAGE_REGION = _get_config("MINIO_STORAGE_REGION", default="sa")

if STORAGE_TYPE == "MINIO":
    required_minio = (
        "MINIO_ACCESS_KEY_ID",
        "MINIO_SECRET_ACCESS_KEY",
        "MINIO_STORAGE_BUCKET_NAME",
        "MINIO_CUSTOM_DOMAIN",
    )
    for key in required_minio:
        if not _get_config(key):
            raise RuntimeError(f"Missing required MINIO configuration: {key}")

EMAIL_TYPE = _get_config("EMAIL_TYPE", default=None)

# -------------------------------------------------------------------
# CORS / Security
# -------------------------------------------------------------------
_platform_scheme = "https" if SECURED_PLATFORM else "http"
_platform_origins = [f"{_platform_scheme}://{host}" for host in _platform_hosts_with_port if host]

CORS_ALLOW_ALL_ORIGINS = _truthy(os.getenv("CORS_ALLOW_ALL", "1"))
CORS_ALLOWED_ORIGINS = sorted(
    set(_split_csv(os.getenv("CORS_ALLOWED_ORIGINS", "")) + _platform_origins)
)
CSRF_TRUSTED_ORIGINS = sorted(
    set(_split_csv(os.getenv("CSRF_TRUSTED_ORIGINS", "")) + _platform_origins)
)

if MANAGE_SSL_DIRECTLY:
    SECURE_SSL_REDIRECT = SECURED_PLATFORM
    SECURE_PROXY_SSL_HEADER = None
else:
    SECURE_SSL_REDIRECT = False
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SESSION_COOKIE_SECURE = _truthy(
    os.getenv("SESSION_COOKIE_SECURE"), default=SECURED_PLATFORM
)
CSRF_COOKIE_SECURE = _truthy(
    os.getenv("CSRF_COOKIE_SECURE"), default=SECURED_PLATFORM
)

if SECURED_PLATFORM:
    SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

_core_origins = [
    _origin_from_url(CORE_URL),
    _origin_from_url(ALTERNATIVE_CORE_URL),
    _origin_from_url(INTERNAL_CORE_URL),
]
_ws_origin = _origin_from_url(WEBSOCKET_URL)

CSP_DEFAULT_SRC = ["'self'"] + [origin for origin in _platform_origins if origin]
CSP_CONNECT_SRC = ["'self'"] + [
    origin for origin in (_platform_origins + _core_origins) if origin
]
if _ws_origin:
    CSP_CONNECT_SRC.append(_ws_origin)
CSP_SCRIPT_SRC = ["'self'", "'unsafe-inline'"]
CSP_STYLE_SRC = ["'self'", "'unsafe-inline'"]
CSP_IMG_SRC = ["'self'", "data:"]
CSP_FONT_SRC = ["'self'", "data:"]

# -------------------------------------------------------------------
# i18n / Defaults
# -------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("TZ", "UTC")
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
