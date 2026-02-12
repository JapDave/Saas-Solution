from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponseRedirect
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from apps.authentication.views import (
    SessionTokenObtainPairView,
    SessionTokenRefreshView,
)

urlpatterns = [
    path("", lambda r: HttpResponseRedirect("/api/docs/")),
    path("admin/", admin.site.urls),
    # Auth
    path("api/auth/token/", SessionTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", SessionTokenRefreshView.as_view(), name="token_refresh"),
    path("api/", include("apps.authentication.urls")),
    # OpenAPI / Docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),

    # App routers (these will 404 until you implement them; that’s OK)
    path("api/", include("apps.accounts.urls")),
    path("api/", include("apps.organizations.urls")),
    path("api/", include("apps.users.urls")),
    path("api/", include("apps.roles.urls")),
    path("api/", include("apps.subscriptions.urls")),
    path("api/", include("apps.teams.urls")),
    path("api/", include("apps.files.urls")),
    path("api/", include("apps.products.urls")),
    path("api/", include("apps.agents.urls")),
    path("api/", include("apps.channels.urls")),
    path("api/", include("apps.flows.urls")),
    path("api/", include("apps.integrations.urls")),
    path("api/", include("apps.knowledge_base.urls")),
    path("api/", include("apps.llms.urls")),
    path("api/", include("apps.tools.urls")),
    path("api/", include("apps.common.urls")),
]

handler400 = "apps.common.error_views.json_bad_request"
handler403 = "apps.common.error_views.json_permission_denied"
handler404 = "apps.common.error_views.json_not_found"
handler500 = "apps.common.error_views.json_server_error"
