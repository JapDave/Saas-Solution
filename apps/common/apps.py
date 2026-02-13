from django.apps import AppConfig

class CommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.common"
    verbose_name = "Common"

    def ready(self) -> None:
        from . import signals  # noqa: F401

        signals.register_audit_signals()
        signals.register_permission_cache_signals()
        self._disable_auth_permission_signals_for_pytest()

    @staticmethod
    def _disable_auth_permission_signals_for_pytest() -> None:
        import os
        if "PYTEST_CURRENT_TEST" not in os.environ:
            return
        try:
            from django.db.models.signals import post_migrate
            from django.contrib.auth.management import create_permissions
            from django.contrib.contenttypes.management import create_contenttypes

            post_migrate.disconnect(
                create_permissions,
                dispatch_uid="django.contrib.auth.management.create_permissions",
            )
            post_migrate.disconnect(
                create_contenttypes,
                dispatch_uid="django.contrib.contenttypes.management.create_contenttypes",
            )
        except Exception:
            # Best-effort only; tests will still run if disconnect fails.
            return
