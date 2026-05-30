from decimal import Decimal, InvalidOperation
from datetime import date
import calendar

from django.contrib.auth.models import User
from django.db import models as django_models
from django.db.models import Sum
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import (
    FinancialAccount,
    Fund,
    MonthlyBudgetSetup,
    MonthCycle,
    Transfer,
    Expense,
    Alert,
    NetWorthSnapshot,
    MonthSummary,
)
from .serializers import (
    RegisterSerializer,
    UserSerializer,
    CustomTokenObtainPairSerializer,
    FinancialAccountSerializer,
    FundSerializer,
    FundCreateSerializer,
    MonthlyBudgetSetupSerializer,
    MonthCycleSerializer,
    TransferSerializer,
    TransferCreateSerializer,
    ExpenseSerializer,
    AlertSerializer,
    NetWorthSnapshotSerializer,
    MonthSummarySerializer,
)
from .services import (
    run_setup_balances,
    run_income_allocation,
    run_survival_draw,
    run_transfer,
    run_expense,
    run_close_month,
)


def _get_account(user) -> FinancialAccount | None:
    """Get the user's FinancialAccount or None."""
    try:
        return FinancialAccount.objects.get(user=user)
    except FinancialAccount.DoesNotExist:
        return None


def _account_not_found_response() -> Response:
    return Response(
        {"detail": "Financial account not found. Complete setup first."},
        status=status.HTTP_404_NOT_FOUND,
    )


def _parse_decimal(value, field_name="amount") -> Decimal:
    """Parse a decimal from request data."""
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({field_name: "Enter a valid number."})


def _get_system_fund_or_404(account: FinancialAccount, name: str):
    try:
        return Fund.objects.get(account=account, name=name, type=Fund.TYPE_SYSTEM)
    except Fund.DoesNotExist:
        return None


def _parse_iso_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValidationError({"date": "Enter a valid date in YYYY-MM-DD format."})


def _account_profile(account) -> dict:
    """
    Returns a snapshot of the account's current financial state.
    Used in almost every response so the frontend can update in one shot.
    """
    funds = Fund.objects.filter(account=account, status=Fund.STATUS_ACTIVE)
    net_worth = funds.aggregate(total=Sum("current_balance"))["total"] or Decimal("0.00")
    cycle = MonthCycle.objects.filter(
        account=account,
        status=MonthCycle.STATUS_ACTIVE,
    ).first()

    return {
        "net_worth": str(net_worth),
        "funds": FundSerializer(
            funds.order_by("allocation_priority"),
            many=True,
        ).data,
        "active_cycle": MonthCycleSerializer(cycle).data if cycle else None,
    }


# ── AUTH ──
class RegisterView(generics.CreateAPIView):
    """Create a new user account."""

    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {
                "message": "Account created successfully.",
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


class CustomTokenObtainPairView(TokenObtainPairView):
    """Authenticate and return JWT tokens plus user info."""

    serializer_class = CustomTokenObtainPairSerializer
    permission_classes = [permissions.AllowAny]


class MeView(APIView):
    """Return the authenticated user."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data, status=status.HTTP_200_OK)


# ── ACCOUNT ──
class FinancialAccountView(APIView):
    """Read or update the authenticated user's financial account."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        account = _get_account(request.user)
        if account is None:
            return _account_not_found_response()
        return Response(FinancialAccountSerializer(account).data)

    def patch(self, request):
        account = _get_account(request.user)
        if account is None:
            return _account_not_found_response()
        serializer = FinancialAccountSerializer(account, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)


class FinancialResetView(APIView):
    """Reset all transaction data while preserving funds and budget setup."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        account = _get_account(request.user)
        if account is None:
            return _account_not_found_response()

        Fund.objects.filter(account=account).update(current_balance=Decimal("0.00"))
        MonthCycle.objects.filter(account=account).delete()
        Transfer.objects.filter(account=account).delete()
        Expense.objects.filter(account=account).delete()
        Alert.objects.filter(account=account).delete()
        NetWorthSnapshot.objects.filter(account=account).delete()
        MonthSummary.objects.filter(account=account).delete()

        return Response(
            {
                "message": "Financial data reset. Your funds and budget setup are preserved.",
                "profile": _account_profile(account),
            },
            status=status.HTTP_200_OK,
        )


# ── SETUP ──
class SetupStatusView(APIView):
    """Return setup completion flags for the authenticated user."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        account = _get_account(request.user)
        has_account = account is not None
        has_custom_funds = (
            Fund.objects.filter(account=account, type=Fund.TYPE_GOAL).exists()
            if account
            else False
        )
        has_balances = (
            NetWorthSnapshot.objects.filter(account=account).count() > 1
            if account
            else False
        )
        has_budget = (
            MonthlyBudgetSetup.objects.filter(account=account).exists()
            if account
            else False
        )

        return Response(
            {
                "has_account": has_account,
                "has_custom_funds": has_custom_funds,
                "has_balances": has_balances,
                "has_budget": has_budget,
                "setup_complete": all([has_account, has_balances, has_budget]),
            },
            status=status.HTTP_200_OK,
        )


class SetupBalancesView(APIView):
    """Save initial fund balances from the setup wizard."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        account = _get_account(request.user)
        if account is None:
            return _account_not_found_response()

        raw = request.data.get("balances", {})
        if not isinstance(raw, dict) or not raw:
            return Response(
                {"error": "Provide a balances dict of {fund_id: amount}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        balances = {}
        for fund_id, amount in raw.items():
            try:
                balances[int(fund_id)] = _parse_decimal(
                    amount,
                    field_name=f"balances.{fund_id}",
                )
            except (TypeError, ValueError):
                return Response(
                    {"error": f"Invalid fund id: {fund_id}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            snapshot = run_setup_balances(account, balances)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        funds = Fund.objects.filter(account=account).order_by("allocation_priority")
        return Response(
            {
                "message": "Balances saved.",
                "net_worth": snapshot.net_worth,
                "funds": FundSerializer(funds, many=True).data,
                "profile": _account_profile(account),
            },
            status=status.HTTP_200_OK,
        )


class SetupBudgetView(APIView):
    """Create the first monthly budget setup."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        account = _get_account(request.user)
        if account is None:
            return _account_not_found_response()

        data = request.data.copy()
        if "effective_from" not in data:
            data["effective_from"] = str(timezone.localdate())

        serializer = MonthlyBudgetSetupSerializer(
            data=data,
            context={"account": account},
        )
        serializer.is_valid(raise_exception=True)
        setup = serializer.save(account=account)

        return Response(
            MonthlyBudgetSetupSerializer(
                setup,
                context={"account": account},
            ).data,
            status=status.HTTP_201_CREATED,
        )


# ── FUNDS ──
class FundListCreateView(APIView):
    """List funds or create a new goal fund."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        account = _get_account(request.user)
        if account is None:
            return _account_not_found_response()
        funds = Fund.objects.filter(account=account).order_by("allocation_priority")
        return Response(FundSerializer(funds, many=True).data, status=status.HTTP_200_OK)

    def post(self, request):
        account = _get_account(request.user)
        if account is None:
            return _account_not_found_response()

        serializer = FundCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        last_priority = (
            Fund.objects.filter(account=account)
            .order_by("-allocation_priority")
            .first()
        )
        next_priority = (last_priority.allocation_priority + 1) if last_priority else 4

        fund = serializer.save(
            account=account,
            type=Fund.TYPE_GOAL,
            allocation_priority=next_priority,
            skip_on_low_income=True,
        )
        return Response(FundSerializer(fund).data, status=status.HTTP_201_CREATED)


class FundDetailView(APIView):
    """Retrieve or update one fund scoped to the current account."""

    permission_classes = [permissions.IsAuthenticated]

    allowed_patch_fields = {
        "name",
        "icon",
        "color",
        "monthly_allocation",
        "allocation_priority",
        "skip_on_low_income",
        "target_amount",
        "target_date",
    }

    def _get_fund(self, request, pk):
        account = _get_account(request.user)
        if account is None:
            return None, None
        try:
            return account, Fund.objects.get(pk=pk, account=account)
        except Fund.DoesNotExist:
            return account, None

    def get(self, request, pk):
        account, fund = self._get_fund(request, pk)
        if account is None:
            return _account_not_found_response()
        if fund is None:
            return Response({"detail": "Fund not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(FundSerializer(fund).data, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        account, fund = self._get_fund(request, pk)
        if account is None:
            return _account_not_found_response()
        if fund is None:
            return Response({"detail": "Fund not found."}, status=status.HTTP_404_NOT_FOUND)

        data = {
            key: value
            for key, value in request.data.items()
            if key in self.allowed_patch_fields
        }
        if fund.type == Fund.TYPE_SYSTEM:
            data.pop("name", None)

        serializer = FundSerializer(fund, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        fund = serializer.save()

        return Response(FundSerializer(fund).data, status=status.HTTP_200_OK)


class FundReorderView(APIView):
    """Reorder funds by allocation priority."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        account = _get_account(request.user)
        if account is None:
            return _account_not_found_response()

        order = request.data.get("order", [])
        if not isinstance(order, list):
            return Response(
                {"error": "Provide an order list of fund IDs."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        for priority, fund_id in enumerate(order, start=1):
            Fund.objects.filter(id=fund_id, account=account).update(
                allocation_priority=priority,
            )

        funds = Fund.objects.filter(account=account).order_by("allocation_priority")
        return Response(
            FundSerializer(funds, many=True).data,
            status=status.HTTP_200_OK,
        )


class FundCloseFundView(APIView):
    """Close a goal fund and move its remaining balance to Cash on Hand."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        account = _get_account(request.user)
        if account is None:
            return _account_not_found_response()
        try:
            fund = Fund.objects.get(pk=pk, account=account)
        except Fund.DoesNotExist:
            return Response({"detail": "Fund not found."}, status=status.HTTP_404_NOT_FOUND)

        if fund.type == Fund.TYPE_SYSTEM:
            return Response(
                {"error": "System funds cannot be closed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        note = request.data.get("note", "").strip()
        if not note:
            return Response(
                {"error": "A note is required when closing a fund."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cash_on_hand = _get_system_fund_or_404(account, Fund.SYSTEM_CASH_ON_HAND)
        if cash_on_hand is None:
            return Response(
                {"detail": "Cash on Hand fund not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        remaining = fund.current_balance
        if remaining > Decimal("0.00"):
            try:
                run_transfer(
                    account=account,
                    cycle=None,
                    from_fund=fund,
                    to_fund=cash_on_hand,
                    amount=remaining,
                    transfer_type=Transfer.TYPE_GOAL_COMPLETED,
                    note=note,
                )
            except ValueError as exc:
                return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        fund.close(note=note)
        fund.refresh_from_db()
        return Response(
            {
                "message": f"{fund.name} closed. ₱{remaining:,.2f} moved to Cash on Hand.",
                "fund": FundSerializer(fund).data,
                "transferred": str(remaining),
                "profile": _account_profile(account),
            },
            status=status.HTTP_200_OK,
        )


class FundAllocationSuggestionView(APIView):
    """Return a 50/30/20 allocation suggestion for the active setup."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        account = _get_account(request.user)
        if account is None:
            return _account_not_found_response()

        setup = MonthlyBudgetSetup.get_active(account)
        if setup is None:
            return Response(
                {"detail": "No budget setup found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        income = setup.estimated_monthly_income
        funds_total = (
            Fund.objects.filter(account=account, status=Fund.STATUS_ACTIVE).aggregate(
                total=Sum("monthly_allocation")
            )["total"]
            or Decimal("0.00")
        )
        return Response(
            {
                "estimated_income": income,
                "suggestion_50_30_20": {
                    "needs": round(income * Decimal("0.50"), 2),
                    "wants": round(income * Decimal("0.30"), 2),
                    "savings": round(income * Decimal("0.20"), 2),
                },
                "current": {
                    "needs": setup.needs_budget,
                    "wants": setup.wants_budget,
                    "funds_total": funds_total,
                },
            },
            status=status.HTTP_200_OK,
        )


# ── BUDGET ──
class MonthlyBudgetSetupListView(APIView):
    """List budget setup history newest first."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        account = _get_account(request.user)
        if account is None:
            return _account_not_found_response()
        setups = MonthlyBudgetSetup.objects.filter(account=account).order_by(
            "-effective_from",
        )
        serializer = MonthlyBudgetSetupSerializer(
            setups,
            many=True,
            context={"account": account},
        )
        return Response(serializer.data, status=status.HTTP_200_OK)


class MonthlyBudgetSetupUpdateView(SetupBudgetView):
    """Create a new budget setup row while preserving history."""


# ── INCOME ──
class IncomeView(APIView):
    """Create a month cycle and allocate entered income."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        account = _get_account(request.user)
        if account is None:
            return _account_not_found_response()

        income = _parse_decimal(request.data.get("income", "0"), "income")
        if income < Decimal("0.00"):
            return Response(
                {"error": "Income cannot be negative."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        now = timezone.now()
        try:
            year = int(request.data.get("year", now.year))
            month = int(request.data.get("month", now.month))
        except (TypeError, ValueError):
            return Response(
                {"error": "Year and month must be valid integers."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        MonthCycle.objects.filter(
            account=account,
            status=MonthCycle.STATUS_ACTIVE,
        ).update(status=MonthCycle.STATUS_CLOSED)

        setup = MonthlyBudgetSetup.get_active(account)
        if setup is None:
            return Response(
                {"error": "No budget setup found. Complete setup first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            cycle = MonthCycle.objects.create(
                account=account,
                budget_setup=setup,
                year=year,
                month=month,
                status=MonthCycle.STATUS_ACTIVE,
            )
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        cycle = run_income_allocation(account, cycle, income)
        if cycle.income_scenario == MonthCycle.SCENARIO_ZERO:
            return Response(
                {
                    "cycle": MonthCycleSerializer(cycle).data,
                    "profile": _account_profile(account),
                    "survival_mode": True,
                    "survival_prompt": (
                        f"No income this month. Use Emergency Fund to cover "
                        f"₱{cycle.needs_budget_used:,.2f} needs budget?"
                    ),
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "cycle": MonthCycleSerializer(cycle).data,
                "profile": _account_profile(account),
                "survival_mode": False,
            },
            status=status.HTTP_200_OK,
        )


class SurvivalDrawView(APIView):
    """Draw from Emergency Fund for the active zero-income cycle."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        account = _get_account(request.user)
        if account is None:
            return _account_not_found_response()

        cycle = (
            MonthCycle.objects.filter(
                account=account,
                status=MonthCycle.STATUS_ACTIVE,
            )
            .order_by("-created_at")
            .first()
        )
        if cycle is None or cycle.income_scenario != MonthCycle.SCENARIO_ZERO:
            return Response(
                {"error": "No active zero-income cycle found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            transfer = run_survival_draw(account, cycle)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "message": f"₱{transfer.amount:,.2f} moved from Emergency Fund to Cash on Hand.",
                "transfer": TransferSerializer(transfer).data,
                "profile": _account_profile(account),
            },
            status=status.HTTP_200_OK,
        )


# ── TRANSFERS ──
class TransferCreateView(APIView):
    """Create a transfer using the service transfer engine."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        account = _get_account(request.user)
        if account is None:
            return _account_not_found_response()

        serializer = TransferCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from_fund = serializer.validated_data.get("from_fund")
        to_fund = serializer.validated_data.get("to_fund")

        if from_fund and from_fund.account_id != account.id:
            return Response(
                {"error": "Source fund not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if to_fund is None or to_fund.account_id != account.id:
            return Response(
                {"error": "Destination fund not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        cycle = MonthCycle.objects.filter(
            account=account,
            status=MonthCycle.STATUS_ACTIVE,
        ).first()

        try:
            transfer = run_transfer(
                account=account,
                cycle=cycle,
                from_fund=from_fund,
                to_fund=to_fund,
                amount=serializer.validated_data["amount"],
                transfer_type=serializer.validated_data["transfer_type"],
                note=serializer.validated_data.get("note", ""),
                transfer_date=serializer.validated_data.get("date"),
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "transfer": TransferSerializer(transfer).data,
                "profile": _account_profile(account),
            },
            status=status.HTTP_201_CREATED,
        )


class TransferListView(APIView):
    """List transfers with optional fund, type, and limit filters."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        account = _get_account(request.user)
        if account is None:
            return _account_not_found_response()

        qs = Transfer.objects.filter(account=account).order_by("-date", "-created_at")
        fund_id = request.query_params.get("fund")
        if fund_id:
            qs = qs.filter(
                django_models.Q(from_fund_id=fund_id)
                | django_models.Q(to_fund_id=fund_id)
            )

        transfer_type = request.query_params.get("type")
        if transfer_type:
            qs = qs.filter(transfer_type=transfer_type)

        try:
            limit = min(int(request.query_params.get("limit", 50)), 200)
        except (TypeError, ValueError):
            limit = 50

        return Response(
            TransferSerializer(qs[:limit], many=True).data,
            status=status.HTTP_200_OK,
        )


class AddMoneyView(APIView):
    """Add external money directly to Cash on Hand."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        account = _get_account(request.user)
        if account is None:
            return _account_not_found_response()

        amount = _parse_decimal(request.data.get("amount", "0"))
        note = request.data.get("note", "").strip()
        if not note:
            return Response(
                {"error": "A note is required when adding external money."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cash_on_hand = _get_system_fund_or_404(account, Fund.SYSTEM_CASH_ON_HAND)
        if cash_on_hand is None:
            return Response(
                {"detail": "Cash on Hand fund not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        cycle = MonthCycle.objects.filter(
            account=account,
            status=MonthCycle.STATUS_ACTIVE,
        ).first()
        parsed_date = _parse_iso_date(request.data.get("date"))

        try:
            transfer = run_transfer(
                account=account,
                cycle=cycle,
                from_fund=None,
                to_fund=cash_on_hand,
                amount=amount,
                transfer_type=Transfer.TYPE_EXTERNAL_ADD,
                note=note,
                transfer_date=parsed_date,
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "transfer": TransferSerializer(transfer).data,
                "profile": _account_profile(account),
            },
            status=status.HTTP_201_CREATED,
        )


# ── EXPENSES ──
class ExpenseCreateView(APIView):
    """Create an expense and deduct it from Cash on Hand."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        account = _get_account(request.user)
        if account is None:
            return _account_not_found_response()

        cycle = MonthCycle.objects.filter(
            account=account,
            status=MonthCycle.STATUS_ACTIVE,
        ).first()
        if cycle is None:
            return Response(
                {"error": "No active cycle. Submit income first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ExpenseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        expense_date = serializer.validated_data.get("date") or timezone.localdate()
        expense_data = {
            key: value
            for key, value in serializer.validated_data.items()
            if key != "date"
        }

        expense = Expense.objects.create(
            account=account,
            cycle=cycle,
            date=expense_date,
            **expense_data,
        )

        try:
            new_alerts = run_expense(account, cycle, expense)
        except ValueError as exc:
            expense.delete()
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        cycle.refresh_from_db()
        return Response(
            {
                "expense": ExpenseSerializer(expense).data,
                "cycle": MonthCycleSerializer(cycle).data,
                "profile": _account_profile(account),
                "alerts": AlertSerializer(new_alerts, many=True).data,
            },
            status=status.HTTP_201_CREATED,
        )


class ExpenseListView(APIView):
    """List expenses, defaulting to the active cycle."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        account = _get_account(request.user)
        if account is None:
            return _account_not_found_response()

        qs = Expense.objects.filter(account=account).order_by("-date", "-created_at")
        cycle_id = request.query_params.get("cycle")
        if cycle_id:
            qs = qs.filter(cycle_id=cycle_id)
        else:
            active_cycle = MonthCycle.objects.filter(
                account=account,
                status=MonthCycle.STATUS_ACTIVE,
            ).first()
            qs = qs.filter(cycle=active_cycle) if active_cycle else qs.none()

        category = request.query_params.get("category")
        if category:
            qs = qs.filter(category=category)

        try:
            limit = min(int(request.query_params.get("limit", 100)), 500)
        except (TypeError, ValueError):
            limit = 100

        return Response(
            ExpenseSerializer(qs[:limit], many=True).data,
            status=status.HTTP_200_OK,
        )


class DailyLimitView(APIView):
    """Return today's spending and suggested daily limit."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        account = _get_account(request.user)
        if account is None:
            return _account_not_found_response()

        cycle = MonthCycle.objects.filter(
            account=account,
            status=MonthCycle.STATUS_ACTIVE,
        ).first()
        if cycle is None:
            return Response(
                {"error": "No active cycle. Submit income first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        today = timezone.localdate()
        _, total_days = calendar.monthrange(today.year, today.month)
        remaining_days = max(1, total_days - today.day)
        daily_limit = cycle.remaining_budget / Decimal(remaining_days)
        today_spent = (
            Expense.objects.filter(cycle=cycle, date=today).aggregate(
                total=Sum("amount")
            )["total"]
            or Decimal("0.00")
        )

        return Response(
            {
                "daily_limit": daily_limit,
                "remaining_budget": cycle.remaining_budget,
                "remaining_days": remaining_days,
                "today_spent": today_spent,
            },
            status=status.HTTP_200_OK,
        )


# ── ALERTS ──
class AlertListView(APIView):
    """List unread alerts by default, or all alerts with all=true."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        account = _get_account(request.user)
        if account is None:
            return _account_not_found_response()

        qs = Alert.objects.filter(account=account).order_by("-created_at")
        if request.query_params.get("all") != "true":
            qs = qs.filter(is_read=False)
        return Response(AlertSerializer(qs, many=True).data, status=status.HTTP_200_OK)


class AlertMarkReadView(APIView):
    """Mark one alert as read."""

    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        account = _get_account(request.user)
        if account is None:
            return _account_not_found_response()

        try:
            alert = Alert.objects.get(pk=pk, account=account)
        except Alert.DoesNotExist:
            return Response({"detail": "Alert not found."}, status=status.HTTP_404_NOT_FOUND)

        alert.is_read = True
        alert.save(update_fields=["is_read"])
        return Response(
            {
                "alert": AlertSerializer(alert).data,
                "profile": _account_profile(account),
            },
            status=status.HTTP_200_OK,
        )


# ── SNAPSHOTS AND SUMMARY ──
class NetWorthSnapshotListView(APIView):
    """List recent net worth snapshots."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        account = _get_account(request.user)
        if account is None:
            return _account_not_found_response()

        try:
            limit = min(int(request.query_params.get("limit", 30)), 200)
        except (TypeError, ValueError):
            limit = 30

        qs = NetWorthSnapshot.objects.filter(account=account).order_by("-captured_at")
        return Response(
            NetWorthSnapshotSerializer(qs[:limit], many=True).data,
            status=status.HTTP_200_OK,
        )


class CloseMonthView(APIView):
    """Close the active month and return its summary."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        account = _get_account(request.user)
        if account is None:
            return _account_not_found_response()

        cycle = MonthCycle.objects.filter(
            account=account,
            status=MonthCycle.STATUS_ACTIVE,
        ).first()
        if cycle is None:
            return Response(
                {"detail": "No active cycle to close."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            summary = run_close_month(account, cycle)
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "message": "Month closed successfully.",
                "summary": MonthSummarySerializer(summary).data,
                "profile": _account_profile(account),
            },
            status=status.HTTP_200_OK,
        )
