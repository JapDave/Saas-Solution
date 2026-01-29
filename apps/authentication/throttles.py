from rest_framework.throttling import SimpleRateThrottle
from django.conf import settings


class _BaseAuthThrottle(SimpleRateThrottle):
    scope = ""
    rate = None

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        return self.cache_format % {
            "scope": self.scope,
            "ident": ident,
        }

    @classmethod
    def configured_rate(cls, setting_key: str, default: str) -> str:
        return getattr(settings, setting_key, default)


class LoginRateThrottle(_BaseAuthThrottle):
    scope = "auth_login"
    rate = _BaseAuthThrottle.configured_rate("AUTH_RATE_LIMIT_LOGIN", "10/min")


class RefreshRateThrottle(_BaseAuthThrottle):
    scope = "auth_refresh"
    rate = _BaseAuthThrottle.configured_rate("AUTH_RATE_LIMIT_REFRESH", "30/min")


class LogoutRateThrottle(_BaseAuthThrottle):
    scope = "auth_logout"
    rate = _BaseAuthThrottle.configured_rate("AUTH_RATE_LIMIT_LOGOUT", "60/min")


class ContextSwitchRateThrottle(_BaseAuthThrottle):
    scope = "auth_context_switch"
    rate = _BaseAuthThrottle.configured_rate("AUTH_RATE_LIMIT_CONTEXT_SWITCH", "30/min")


class PasswordResetRateThrottle(_BaseAuthThrottle):
    scope = "auth_password_reset"
    rate = _BaseAuthThrottle.configured_rate("AUTH_RATE_LIMIT_PASSWORD_RESET", "5/hour")


class PermissionCheckRateThrottle(_BaseAuthThrottle):
    scope = "authz_permission_check"
    rate = _BaseAuthThrottle.configured_rate("AUTH_RATE_LIMIT_PERMISSION_CHECK", "200/min")
