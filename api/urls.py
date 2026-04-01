# api/urls.py
#
# ┌──────────────────────────────────────────────────────────────────────────────┐
# │  Method        │  URL                          │  Description                │
# ├────────────────┼───────────────────────────────┼─────────────────────────────┤
# │  POST          │  /api/auth/register/           │  Create account             │
# │  POST          │  /api/auth/token/              │  Login → get tokens         │
# │  POST          │  /api/auth/token/refresh/      │  Refresh access token       │
# │  GET           │  /api/auth/me/                 │  Get current user           │
# ├────────────────┼───────────────────────────────┼─────────────────────────────┤
# │  GET / PATCH   │  /api/finance/profile/         │  Financial profile          │
# │  GET           │  /api/finance/snapshots/       │  Net worth history          │
# │  GET           │  /api/finance/cycles/          │  Month cycle history        │
# ├────────────────┼───────────────────────────────┼─────────────────────────────┤
# │  POST          │  /api/income/                  │  Run allocation engine      │
# │  POST          │  /api/invest/                  │  savings → investments      │
# │  GET           │  /api/cycle/current/           │  Active cycle               │
# ├────────────────┼───────────────────────────────┼─────────────────────────────┤
# │  POST          │  /api/expenses/                │  Log expense                │
# │  GET           │  /api/expenses/                │  List expenses              │
# │  GET           │  /api/expenses/daily-limit/    │  Daily spending limit       │
# ├────────────────┼───────────────────────────────┼─────────────────────────────┤
# │  GET           │  /api/alerts/                  │  List unread alerts         │
# │  PATCH         │  /api/alerts/<id>/read/        │  Mark alert as read         │
# └──────────────────────────────────────────────────────────────────────────────┘

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from api.views import (
    AlertListView,
    AlertMarkReadView,
    CloseMonthView,
    CurrentMonthCycleView,
    CustomTokenObtainPairView,
    DailyLimitView,
    DivestView,
    ExpenseListView,
    ExpenseView,
    FinancialProfileView,
    IncomeView,
    InvestmentAllocationView,
    InvestmentDetailView,
    InvestmentListCreateView,
    InvestView,
    MeView,
    MonthCycleListView,
    NetWorthSnapshotListView,
    RegisterView,
    ReportsView,
    ResetExpensesView,
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
    path("divest/",             DivestView.as_view(),                name="divest"),

    # ── Active cycle ──────────────────────────────────────────────────────
    path("cycle/current/",              CurrentMonthCycleView.as_view(),     name="cycle-current"),
    path("cycle/current/reset-expenses/", ResetExpensesView.as_view(),       name="cycle-reset-expenses"),
    path("cycle/reset-expenses/",       ResetExpensesView.as_view(),         name="cycle-reset-expenses-alias"),

    # ── Expenses ──────────────────────────────────────────────────────────
    path("expenses/",            ExpenseView.as_view(),              name="expense-create"),
    path("expenses/list/",       ExpenseListView.as_view(),          name="expense-list"),
    path("expenses/daily-limit/",DailyLimitView.as_view(),          name="expense-daily-limit"),

    # ── Alerts ────────────────────────────────────────────────────────────
    path("alerts/",              AlertListView.as_view(),            name="alert-list"),
    path("alerts/<int:pk>/read/",AlertMarkReadView.as_view(),        name="alert-mark-read"),

    # ── Investments ───────────────────────────────────────────────────────
    path("investments/",              InvestmentListCreateView.as_view(), name="investment-list-create"),
    path("investments/<int:pk>/",     InvestmentDetailView.as_view(),     name="investment-detail"),
    path("investments/allocation/",   InvestmentAllocationView.as_view(), name="investment-allocation"),

    # ── Month Management ──────────────────────────────────────────────────
    path("month/close/",         CloseMonthView.as_view(),           name="month-close"),

    # ── Reports ───────────────────────────────────────────────────────────
    path("reports/",             ReportsView.as_view(),              name="reports"),
]