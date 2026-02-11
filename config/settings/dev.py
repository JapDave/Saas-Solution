from .base import *

DEBUG = True
ALLOWED_HOSTS = ["*"]

# In dev we keep cookies non-secure for localhost
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False


# Use SMTP/Mailpit when EMAIL_TYPE=LOCAL_SMTP, else default to console
if EMAIL_TYPE and EMAIL_TYPE.upper() == "LOCAL_SMTP":
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
