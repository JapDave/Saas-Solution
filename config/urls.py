from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponseRedirect
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from users.auth import StatusAwareTokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

class StatusAwareTokenObtainPairView(TokenObtainPairView):
    serializer_class = StatusAwareTokenObtainPairSerializer


urlpatterns = [
    path("", lambda r: HttpResponseRedirect("/api/docs/")),  # 👈 root -> Swagger
    path("admin/", admin.site.urls),
    path("api/auth/token/", StatusAwareTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    path("api/", include("accounts.urls")),
    path("api/", include("users.urls")),
    path("api/", include("teams.urls")),
    path("api/", include("roles.urls")),
]
