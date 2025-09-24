from .base import *

DEBUG = True
ALLOWED_HOSTS = ["*"]

# In dev we keep cookies non-secure for localhost
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False


EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
