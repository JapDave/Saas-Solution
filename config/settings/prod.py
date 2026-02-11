from .base import *
import os

DEBUG = False

# Hard-fail if SECRET_KEY is not provided
if SECRET_KEY == "change-me-in-prod":
    raise RuntimeError("SECRET_KEY must be set in production.")

# Security headers
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = SECURE_SSL_REDIRECT if MANAGE_SSL_DIRECTLY else False

# Logging: use JSON to stdout (12factor)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "format": '{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s","request_id":"%(request_id)s","user":"%(user)s","org":"%(org)s","trace_id":"%(trace_id)s","span_id":"%(span_id)s"}'
        },
    },
    "filters": {
        "apm_trace": {"()": "apps.common.logging.APMTraceFilter"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "json", "filters": ["apm_trace"]},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}
