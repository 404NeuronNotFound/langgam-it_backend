# api/urls.py
#
# All authentication endpoints live under /api/auth/
#
# ┌─────────────────────────────────────────────────────────────────┐
# │  Method  │  URL                        │  Description           │
# ├──────────┼─────────────────────────────┼────────────────────────┤
# │  POST    │  /api/auth/register/        │  Create account        │
# │  POST    │  /api/auth/token/           │  Login → get tokens    │
# │  POST    │  /api/auth/token/refresh/   │  Refresh access token  │
# │  GET     │  /api/auth/me/              │  Get current user      │
# └─────────────────────────────────────────────────────────────────┘

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from api.views import (
    CustomTokenObtainPairView,
    MeView,
    RegisterView,
)

urlpatterns = [
    # ── Registration ──────────────────────────────────────────────
    path("auth/register/", RegisterView.as_view(), name="auth-register"),

    # ── Login: returns access + refresh + user info ───────────────
    path("auth/token/", CustomTokenObtainPairView.as_view(), name="auth-token-obtain"),

    # ── Refresh: exchange refresh token for a new access token ────
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="auth-token-refresh"),

    # ── Current authenticated user ────────────────────────────────
    path("auth/me/", MeView.as_view(), name="auth-me"),
]