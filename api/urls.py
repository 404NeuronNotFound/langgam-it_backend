# api/urls.py
#
# ┌──────────────────────────────────────────────────────────────────────────────┐
# │  Method       │  URL                          │  Description                 │
# ├───────────────┼───────────────────────────────┼──────────────────────────────┤
# │  POST         │  /api/auth/register/           │  Create account              │
# │  POST         │  /api/auth/token/              │  Login → get tokens          │
# │  POST         │  /api/auth/token/refresh/      │  Refresh access token        │
# │  GET          │  /api/auth/me/                 │  Get current user            │
# ├───────────────┼───────────────────────────────┼──────────────────────────────┤
# │  GET / PATCH  │  /api/finance/profile/         │  Financial profile           │
# │  GET          │  /api/finance/snapshots/       │  Net worth history           │
# │  GET          │  /api/finance/cycles/          │  Month cycle history         │
# ├───────────────┼───────────────────────────────┼──────────────────────────────┤
# │  POST         │  /api/income/                  │  Run allocation engine       │
# │  POST         │  /api/invest/                  │  savings → investments       │
# │  GET          │  /api/cycle/current/           │  Active cycle                │
# └──────────────────────────────────────────────────────────────────────────────┘

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from api.views import (
    CurrentMonthCycleView,
    CustomTokenObtainPairView,
    FinancialProfileView,
    IncomeView,
    InvestView,
    MeView,
    MonthCycleListView,
    NetWorthSnapshotListView,
    RegisterView,
)

urlpatterns = [
    # ── Auth ──────────────────────────────────────────────────────────────
    path("auth/register/",      RegisterView.as_view(),              name="auth-register"),
    path("auth/token/",         CustomTokenObtainPairView.as_view(), name="auth-token-obtain"),
    path("auth/token/refresh/", TokenRefreshView.as_view(),          name="auth-token-refresh"),
    path("auth/me/",            MeView.as_view(),                    name="auth-me"),

    # ── Finance ───────────────────────────────────────────────────────────
    path("finance/profile/",    FinancialProfileView.as_view(),      name="finance-profile"),
    path("finance/snapshots/",  NetWorthSnapshotListView.as_view(),  name="finance-snapshots"),
    path("finance/cycles/",     MonthCycleListView.as_view(),        name="finance-cycles"),

    # ── Allocation engine ─────────────────────────────────────────────────
    path("income/",             IncomeView.as_view(),                name="income"),
    path("invest/",             InvestView.as_view(),                name="invest"),

    # ── Active cycle ──────────────────────────────────────────────────────
    path("cycle/current/",      CurrentMonthCycleView.as_view(),     name="cycle-current"),
]