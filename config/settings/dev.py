from .base import *

DEBUG = True
ALLOWED_HOSTS = ["*"]

# In dev we keep cookies non-secure for localhost
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False


EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DYNAMIC_RATELIMITS = {"org.create.owner": "20/hour", "org.update.user": "100/hour", "org.read.user": "1000/hour", "org.delete.owner": "10/day", "org.assign.owner": "50/hour", "acc.create.admin": "10/hour", "acc.update.user": "100/hour", "acc.read.user": "1000/hour", "acc.delete.admin": "5/day", "user.create": "50/hour", "user.update": "200/hour", "user.list": "500/hour", "user.membership_add": "100/hour", "user.membership_remove": "100/hour", "user.session_switch": "300/hour"}
