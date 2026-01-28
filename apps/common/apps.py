from django.apps import AppConfig

class CommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.common"
    verbose_name = "Common"

    def ready(self) -> None:
        from . import signals  # noqa: F401

        signals.register_audit_signals()
