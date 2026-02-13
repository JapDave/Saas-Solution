from django.apps import AppConfig

class RolesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.roles"
    verbose_name = "Roles and Permissions"

    def ready(self) -> None:
        try:
            from django.db.models.signals import post_save
            from apps.organizations.models import Organization
            from .signals import ensure_agent_manager_role  # noqa: F401

            post_save.connect(
                ensure_agent_manager_role,
                sender=Organization,
                weak=False,
                dispatch_uid="roles.ensure_agent_manager_role",
            )
        except Exception:
            # Best-effort only; role seeding can be handled by management command.
            return
