from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponseRedirect
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path("", lambda r: HttpResponseRedirect("/api/docs/")),
    path("admin/", admin.site.urls),
    # Auth
    path("api/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
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
]
