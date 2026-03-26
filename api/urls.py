# api/urls.py
#
# ┌──────────────────────────────────────────────────────────────────────────┐
# │  Method       │  URL                          │  Description             │
# ├───────────────┼───────────────────────────────┼──────────────────────────┤
# │  POST         │  /api/auth/register/           │  Create account          │
# │  POST         │  /api/auth/token/              │  Login → get tokens      │
# │  POST         │  /api/auth/token/refresh/      │  Refresh access token    │
# │  GET          │  /api/auth/me/                 │  Get current user        │
# ├───────────────┼───────────────────────────────┼──────────────────────────┤
# │  GET / PATCH  │  /api/finance/profile/         │  Financial profile       │
# │  GET          │  /api/finance/snapshots/       │  Net worth history       │
# └──────────────────────────────────────────────────────────────────────────┘

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from api.views import (
    CustomTokenObtainPairView,
    FinancialProfileView,
    MeView,
    NetWorthSnapshotListView,
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

    # ── Financial profile (GET = read, PATCH = update + snapshot) ─
    path("finance/profile/", FinancialProfileView.as_view(), name="finance-profile"),

    # ── Net worth history (newest first) ──────────────────────────
    path("finance/snapshots/", NetWorthSnapshotListView.as_view(), name="finance-snapshots"),
]