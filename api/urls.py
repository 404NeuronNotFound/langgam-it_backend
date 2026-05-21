from django.urls import path
from rest_framework import permissions
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenRefreshView

from api.views import (
    # Auth
    RegisterView,
    CustomTokenObtainPairView,
    MeView,
    # Account
    FinancialAccountView,
    FinancialResetView,
    # Setup wizard
    SetupStatusView,
    SetupBalancesView,
    SetupBudgetView,
    # Funds
    FundListCreateView,
    FundDetailView,
    FundReorderView,
    FundCloseFundView,
    FundAllocationSuggestionView,
    # Budget
    MonthlyBudgetSetupListView,
    MonthlyBudgetSetupUpdateView,
    # Income
    IncomeView,
    SurvivalDrawView,
    # Transfers
    TransferCreateView,
    TransferListView,
    AddMoneyView,
    # Expenses
    ExpenseCreateView,
    ExpenseListView,
    DailyLimitView,
    # Alerts
    AlertListView,
    AlertMarkReadView,
    # Snapshots + Close
    NetWorthSnapshotListView,
    CloseMonthView,
)

# api/urls.py
#
# All routes mount under /api/ via langgamit_backend/urls.py
#
# ┌──────────────────────────────────────────────────────────────────────────────┐
# │  Method        │  URL                              │  Name                   │
# ├────────────────┼───────────────────────────────────┼─────────────────────────┤
# │  POST          │  /api/auth/register/              │  auth-register          │
# │  POST          │  /api/auth/token/                 │  auth-token-obtain      │
# │  POST          │  /api/auth/token/refresh/         │  auth-token-refresh     │
# │  GET           │  /api/auth/me/                    │  auth-me                │
# ├────────────────┼───────────────────────────────────┼─────────────────────────┤
# │  GET / PATCH   │  /api/account/                    │  account-detail         │
# │  POST          │  /api/account/reset/              │  account-reset          │
# ├────────────────┼───────────────────────────────────┼─────────────────────────┤
# │  GET           │  /api/setup/status/               │  setup-status           │
# │  POST          │  /api/setup/balances/             │  setup-balances         │
# │  POST          │  /api/setup/budget/               │  setup-budget           │
# ├────────────────┼───────────────────────────────────┼─────────────────────────┤
# │  GET / POST    │  /api/funds/                      │  fund-list-create       │
# │  GET           │  /api/funds/allocation-suggestion/│  fund-allocation-suggest│
# │  POST          │  /api/funds/reorder/              │  fund-reorder           │
# │  GET / PATCH   │  /api/funds/<id>/                 │  fund-detail            │
# │  POST          │  /api/funds/<id>/close/           │  fund-close             │
# ├────────────────┼───────────────────────────────────┼─────────────────────────┤
# │  GET           │  /api/budget/                     │  budget-list            │
# │  POST          │  /api/budget/update/              │  budget-update          │
# ├────────────────┼───────────────────────────────────┼─────────────────────────┤
# │  POST          │  /api/income/                     │  income                 │
# │  POST          │  /api/income/survival-draw/       │  income-survival-draw   │
# ├────────────────┼───────────────────────────────────┼─────────────────────────┤
# │  GET / POST    │  /api/transfers/                  │  transfer-list-create   │
# │  POST          │  /api/transfers/add-money/        │  transfer-add-money     │
# ├────────────────┼───────────────────────────────────┼─────────────────────────┤
# │  GET / POST    │  /api/expenses/                   │  expense-list-create    │
# │  GET           │  /api/expenses/daily-limit/       │  expense-daily-limit    │
# ├────────────────┼───────────────────────────────────┼─────────────────────────┤
# │  GET           │  /api/alerts/                     │  alert-list             │
# │  PATCH         │  /api/alerts/<id>/read/           │  alert-mark-read        │
# ├────────────────┼───────────────────────────────────┼─────────────────────────┤
# │  GET           │  /api/networth/snapshots/         │  networth-snapshots     │
# │  POST          │  /api/month/close/                │  month-close            │
# └──────────────────────────────────────────────────────────────────────────────┘


class TransferView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        return TransferListView.as_view()(request._request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        return TransferCreateView.as_view()(request._request, *args, **kwargs)


class ExpenseView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        return ExpenseListView.as_view()(request._request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        return ExpenseCreateView.as_view()(request._request, *args, **kwargs)


urlpatterns = [
    # ── auth ──
    path("auth/register/", RegisterView.as_view(), name="auth-register"),
    path("auth/token/", CustomTokenObtainPairView.as_view(), name="auth-token-obtain"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="auth-token-refresh"),
    path("auth/me/", MeView.as_view(), name="auth-me"),

    # ── account ──
    path("account/", FinancialAccountView.as_view(), name="account-detail"),
    path("account/reset/", FinancialResetView.as_view(), name="account-reset"),

    # ── setup ──
    path("setup/status/", SetupStatusView.as_view(), name="setup-status"),
    path("setup/balances/", SetupBalancesView.as_view(), name="setup-balances"),
    path("setup/budget/", SetupBudgetView.as_view(), name="setup-budget"),

    # ── funds ──
    path("funds/", FundListCreateView.as_view(), name="fund-list-create"),
    path("funds/reorder/", FundReorderView.as_view(), name="fund-reorder"),
    path(
        "funds/allocation-suggestion/",
        FundAllocationSuggestionView.as_view(),
        name="fund-allocation-suggestion",
    ),
    path("funds/<int:pk>/close/", FundCloseFundView.as_view(), name="fund-close"),
    path("funds/<int:pk>/", FundDetailView.as_view(), name="fund-detail"),

    # ── budget ──
    path("budget/", MonthlyBudgetSetupListView.as_view(), name="budget-list"),
    path("budget/update/", MonthlyBudgetSetupUpdateView.as_view(), name="budget-update"),

    # ── income ──
    path(
        "income/survival-draw/",
        SurvivalDrawView.as_view(),
        name="income-survival-draw",
    ),
    path("income/", IncomeView.as_view(), name="income"),

    # ── transfers ──
    path("transfers/", TransferView.as_view(), name="transfer-list-create"),
    path("transfers/add-money/", AddMoneyView.as_view(), name="transfer-add-money"),

    # ── expenses ──
    path("expenses/", ExpenseView.as_view(), name="expense-list-create"),
    path(
        "expenses/daily-limit/",
        DailyLimitView.as_view(),
        name="expense-daily-limit",
    ),

    # ── alerts ──
    path("alerts/", AlertListView.as_view(), name="alert-list"),
    path("alerts/<int:pk>/read/", AlertMarkReadView.as_view(), name="alert-mark-read"),

    # ── snapshots + close ──
    path(
        "networth/snapshots/",
        NetWorthSnapshotListView.as_view(),
        name="networth-snapshots",
    ),
    path("month/close/", CloseMonthView.as_view(), name="month-close"),
]
