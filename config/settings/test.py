"""Isolated local tests; external-service acceptance tests use separate settings."""
import os
for key, value in {
    "SECRET_KEY": "tests-only-not-for-deployment", "CORE_URL": "http://localhost:9000",
    "CORE_TOKEN": "test-placeholder", "CRON_TOKEN": "test-placeholder", "PLATFORM_URL": "localhost",
    "DB_NAME": "tests", "DB_USER": "tests", "DB_PASSWORD": "tests", "DB_HOST": "localhost",
    "ENABLE_APM": "false", "secured_platform": "false",
}.items():
    os.environ.setdefault(key, value)
from .dev import *  # noqa: F403,E402

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
