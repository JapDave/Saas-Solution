from django.urls import path

from apps.authentication.views import (
    PasswordResetConfirmView,
    PasswordResetRequestView,
    SessionLogoutView,
    SessionTokenObtainPairView,
    SessionTokenRefreshView,
)
from apps.authentication.session_views import SessionListView

urlpatterns = [
    path("auth/logout/", SessionLogoutView.as_view(), name="token_logout"),
    path("auth/password-reset/", PasswordResetRequestView.as_view(), name="password_reset"),
    path("auth/password-reset/confirm/", PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("auth/sessions/", SessionListView.as_view(), name="auth_sessions"),
]
