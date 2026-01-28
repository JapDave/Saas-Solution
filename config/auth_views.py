from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


@extend_schema(tags=["Auth"])
class PublicTokenObtainPairView(TokenObtainPairView):
    """JWT access/refresh obtain endpoint (no auth required in schema)."""


@extend_schema(tags=["Auth"])
class PublicTokenRefreshView(TokenRefreshView):
    """JWT refresh endpoint (no auth required in schema)."""
