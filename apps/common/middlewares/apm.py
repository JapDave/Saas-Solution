from __future__ import annotations

from django.utils.deprecation import MiddlewareMixin

from apps.common.audit import set_apm_context


class APMContextMiddleware(MiddlewareMixin):
    """Enrich active spans with user/org/account identifiers when available."""

    def process_request(self, request):
        user = getattr(request, "user", None)
        user_id = getattr(user, "id", None) if getattr(user, "is_authenticated", False) else None

        organization_id = None
        account_id = None
        if hasattr(request, "session"):
            organization_id = request.session.get("active_organization_id")
        if organization_id:
            try:
                from apps.organizations.models import Organization

                account_id = (
                    Organization.objects.filter(id=organization_id)
                    .values_list("account_id", flat=True)
                    .first()
                )
            except Exception:
                account_id = None

        set_apm_context(
            user_id=user_id,
            organization_id=organization_id,
            account_id=account_id,
        )
