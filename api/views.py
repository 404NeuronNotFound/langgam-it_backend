# api/views.py

import calendar
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import Alert, Expense, FinancialProfile, MonthCycle, NetWorthSnapshot, Investment, MonthSummary, InvestmentAllocation
from .serializers import (
    AlertSerializer,
    CustomTokenObtainPairSerializer,
    ExpenseSerializer,
    FinancialProfileSerializer,
    InvestmentAllocationSerializer,
    InvestmentSerializer,
    MonthCycleSerializer,
    MonthSummarySerializer,
    NetWorthSnapshotSerializer,
    RegisterSerializer,
    UserSerializer,
)
from .services import run_allocation_engine, run_expense, run_invest, run_divest


# ──────────────────────────────────────────────────────────────────────
# 1. Register  →  POST /api/auth/register/
# ──────────────────────────────────────────────────────────────────────

class RegisterView(generics.CreateAPIView):
    """
    Create a new user account. No authentication required.

    Request body:
        {
            "username":         "juandelacruz",
            "first_name":       "Juan",
            "last_name":        "dela Cruz",
            "email":            "juan@example.com",
            "password":         "StrongPass123!",
            "confirm_password": "StrongPass123!"
        }

    Success 201:
        { "message": "Account created successfully.", "user": { ... } }
    """

    queryset           = User.objects.all()
    serializer_class   = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {
                "message": "Account created successfully.",
                "user":    UserSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


# ──────────────────────────────────────────────────────────────────────
# 2. Login  →  POST /api/auth/token/
# ──────────────────────────────────────────────────────────────────────

class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Authenticate with username + password.
    Returns access token (30 min), refresh token (1 day), and basic user info.
    """

    serializer_class   = CustomTokenObtainPairSerializer
    permission_classes = [permissions.AllowAny]


# ──────────────────────────────────────────────────────────────────────
# 3. Current user  →  GET /api/auth/me/
# ──────────────────────────────────────────────────────────────────────

class MeView(APIView):
    """Return the authenticated user's profile."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(
            UserSerializer(request.user).data,
            status=status.HTTP_200_OK,
        )


# ──────────────────────────────────────────────────────────────────────
# 4. Financial Profile  →  GET / PATCH /api/finance/profile/
# ──────────────────────────────────────────────────────────────────────

class FinancialProfileView(APIView):
    """
    GET  — returns current bucket values + live net_worth.
    PATCH — updates one or more buckets + captures a NetWorthSnapshot.

    All five bucket fields are optional in a PATCH.
    """

    permission_classes = [permissions.IsAuthenticated]

    def _get_or_create_profile(self, user) -> FinancialProfile:
        profile, _ = FinancialProfile.objects.get_or_create(user=user)
        return profile

    def get(self, request):
        profile = self._get_or_create_profile(request.user)
        return Response(
            FinancialProfileSerializer(profile).data,
            status=status.HTTP_200_OK,
        )

    def patch(self, request):
        profile    = self._get_or_create_profile(request.user)
        serializer = FinancialProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        NetWorthSnapshot.capture(profile)
        return Response(serializer.data, status=status.HTTP_200_OK)


# ──────────────────────────────────────────────────────────────────────
# 5. Net Worth History  →  GET /api/finance/snapshots/
# ──────────────────────────────────────────────────────────────────────

class NetWorthSnapshotListView(generics.ListAPIView):
    """Return the authenticated user's net-worth history, newest first."""

    serializer_class   = NetWorthSnapshotSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return NetWorthSnapshot.objects.filter(user=self.request.user)


# ──────────────────────────────────────────────────────────────────────
# 6. Income + Allocation Engine  →  POST /api/income/
# ──────────────────────────────────────────────────────────────────────

class IncomeView(APIView):
    """
    Record monthly income and run the full allocation pipeline.

    POST  /api/income/

    Request body:
        {
            "income": "35000.00",   -- required; "0" activates survival mode
            "year":   2026,         -- optional; defaults to current UTC year
            "month":  3             -- optional; defaults to current UTC month
        }

    Allocation order (normal mode):
        income → cash_on_hand
             → spendable budget (₱10,000: ₱7k needs + ₱3k wants) — PRIORITY #1
             → emergency_fund   (₱10,000 per cycle, grows continuously) — PRIORITY #2
             → rigs_fund        (up to ₱10,000)
             → savings          (up to ₱20,000)
             → remainder stays in cash_on_hand

    Success 200:
        { "cycle": { ... }, "profile": { ... } }
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        # Accept either "income" or "amount" as the income field name
        raw = request.data.get("income") or request.data.get("amount") or "0"
        try:
            income = Decimal(str(raw))
        except Exception:
            return Response(
                {"error": "Invalid income value."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if income < Decimal("0"):
            return Response(
                {"error": "Income cannot be negative."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        profile, _ = FinancialProfile.objects.get_or_create(user=request.user)

        # Close ALL previous active cycles (each income creates a new cycle)
        MonthCycle.objects.filter(
            user=request.user,
            status=MonthCycle.STATUS_ACTIVE
        ).update(status=MonthCycle.STATUS_CLOSED)

        # Get the last cycle to determine next month/year
        last_cycle = (
            MonthCycle.objects
            .filter(user=request.user)
            .order_by("-year", "-month")
            .first()
        )

        if last_cycle:
            # Increment month, handle year rollover
            year = last_cycle.year
            month = last_cycle.month + 1
            if month > 12:
                month = 1
                year += 1
        else:
            # First cycle ever - use current date
            now = timezone.now()
            year = now.year
            month = now.month

        # Create a NEW cycle with incremented month
        cycle = MonthCycle.objects.create(
            user=request.user,
            year=year,
            month=month,
            income=income,
            status=MonthCycle.STATUS_ACTIVE,
        )

        # Refresh profile from database to ensure we have the latest values
        profile.refresh_from_db()

        cycle = run_allocation_engine(profile, cycle, income)

        return Response(
            {
                "cycle":   MonthCycleSerializer(cycle).data,
                "profile": FinancialProfileSerializer(profile).data,
            },
            status=status.HTTP_200_OK,
        )


# ──────────────────────────────────────────────────────────────────────
# 7. Invest  →  POST /api/invest/
# ──────────────────────────────────────────────────────────────────────

class InvestView(APIView):
    """
    Move funds from savings → investments_total.

    POST  /api/invest/
        { "amount": "5000.00" }

    Requires an active MonthCycle (call POST /api/income/ first).

    Success 200:
        { "profile": { ... } }
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            amount = Decimal(str(request.data.get("amount", "0")))
        except Exception:
            return Response(
                {"error": "Invalid amount value."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cycle = (
            MonthCycle.objects
            .filter(user=request.user, status=MonthCycle.STATUS_ACTIVE)
            .order_by("-year", "-month")
            .first()
        )
        if cycle is None:
            return Response(
                {"error": "No active month cycle. Call POST /api/income/ first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        profile, _ = FinancialProfile.objects.get_or_create(user=request.user)

        try:
            profile = run_invest(profile, cycle, amount)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"profile": FinancialProfileSerializer(profile).data},
            status=status.HTTP_200_OK,
        )


# ──────────────────────────────────────────────────────────────────────
# 8. Divest  →  POST /api/divest/
# ──────────────────────────────────────────────────────────────────────

class DivestView(APIView):
    """
    Move funds from investments_total → savings (reverse of invest).

    POST  /api/divest/
        { "amount": "5000.00" }

    Requires an active MonthCycle (call POST /api/income/ first).

    Success 200:
        { "profile": { ... } }
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            amount = Decimal(str(request.data.get("amount", "0")))
        except Exception:
            return Response(
                {"error": "Invalid amount value."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cycle = (
            MonthCycle.objects
            .filter(user=request.user, status=MonthCycle.STATUS_ACTIVE)
            .order_by("-year", "-month")
            .first()
        )
        if cycle is None:
            return Response(
                {"error": "No active month cycle. Call POST /api/income/ first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        profile, _ = FinancialProfile.objects.get_or_create(user=request.user)

        try:
            profile = run_divest(profile, cycle, amount)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"profile": FinancialProfileSerializer(profile).data},
            status=status.HTTP_200_OK,
        )


# ──────────────────────────────────────────────────────────────────────
# 8. Month Cycle History  →  GET /api/finance/cycles/
# ──────────────────────────────────────────────────────────────────────

class MonthCycleListView(generics.ListAPIView):
    """Return all MonthCycles for the authenticated user, newest first."""

    serializer_class   = MonthCycleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            MonthCycle.objects
            .filter(user=self.request.user)
            .prefetch_related("allocation_logs")
        )


# ──────────────────────────────────────────────────────────────────────
# 9. Current Active Cycle  →  GET /api/cycle/current/
# ──────────────────────────────────────────────────────────────────────

class CurrentMonthCycleView(APIView):
    """
    Return the most recent active MonthCycle with calculated remaining amounts.

    Returns 404 if no active cycle exists (user has not submitted income yet).
    
    Response includes:
        - All cycle fields from MonthCycleSerializer
        - needs_remaining: expenses_budget - (total needs expenses)
        - wants_remaining: wants_budget - (total wants expenses)
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        cycle = (
            MonthCycle.objects
            .filter(user=request.user, status=MonthCycle.STATUS_ACTIVE)
            .prefetch_related("allocation_logs")
            .order_by("-year", "-month")
            .first()
        )
        if cycle is None:
            return Response(
                {"detail": "No active cycle. Submit income via POST /api/income/."},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        # Calculate remaining amounts for each category
        needs_spent = (
            Expense.objects
            .filter(cycle=cycle, category=Expense.CATEGORY_NEEDS)
            .aggregate(total=models.Sum("amount"))["total"] or Decimal("0.00")
        )
        
        wants_spent = (
            Expense.objects
            .filter(cycle=cycle, category=Expense.CATEGORY_WANTS)
            .aggregate(total=models.Sum("amount"))["total"] or Decimal("0.00")
        )
        
        needs_remaining = cycle.expenses_budget - needs_spent
        wants_remaining = cycle.wants_budget - wants_spent
        
        # Serialize cycle data and add remaining amounts
        data = MonthCycleSerializer(cycle).data
        data["needs_remaining"] = needs_remaining
        data["wants_remaining"] = wants_remaining
        data["needs_spent"] = needs_spent
        data["wants_spent"] = wants_spent
        
        return Response(data, status=status.HTTP_200_OK)


# ──────────────────────────────────────────────────────────────────────
# 10. Log Expense  →  POST /api/expenses/
# ──────────────────────────────────────────────────────────────────────

class ExpenseView(APIView):
    """
    Log a spending transaction for the current active cycle.

    POST  /api/expenses/

    Request body:
        {
            "amount":      "250.00",
            "category":    "needs",        -- "needs" | "wants"
            "description": "Groceries",    -- optional
            "date":        "2026-03-28"    -- optional; defaults to today
        }

    What happens on success
    -----------------------
    1. Expense record is created and linked to the active cycle.
    2. cash_on_hand is reduced by amount.
    3. The correct budget bucket is reduced (expenses_budget or wants_budget).
    4. remaining_budget is reduced.
    5. AI monitoring engine runs (Steps 16–19).
    6. Any triggered alerts are returned alongside the expense.

    Success 201:
        {
            "expense":  { ... },
            "profile":  { ... updated buckets ... },
            "cycle":    { ... updated budgets ... },
            "alerts":   [ ... any new alerts ... ]
        }
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        # Resolve active cycle
        cycle = (
            MonthCycle.objects
            .filter(user=request.user, status=MonthCycle.STATUS_ACTIVE)
            .order_by("-year", "-month")
            .first()
        )
        if cycle is None:
            return Response(
                {"error": "No active month cycle. Submit income via POST /api/income/ first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        profile, _ = FinancialProfile.objects.get_or_create(user=request.user)

        # Validate incoming data
        serializer = ExpenseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        amount   = serializer.validated_data["amount"]
        category = serializer.validated_data["category"]

        # Guard: cannot spend more than what's in cash_on_hand
        if amount > profile.cash_on_hand:
            return Response(
                {
                    "error": (
                        f"Insufficient cash on hand. "
                        f"Available: ₱{profile.cash_on_hand:,.2f}, "
                        f"requested: ₱{amount:,.2f}."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Resolve expense date (default to today)
        expense_date = serializer.validated_data.get("date") or timezone.localdate()

        # Persist the expense record
        expense = Expense.objects.create(
            user        = request.user,
            cycle       = cycle,
            amount      = amount,
            category    = category,
            description = serializer.validated_data.get("description", ""),
            date        = expense_date,
        )

        # Run deduction + monitoring engine
        new_alerts = run_expense(profile, cycle, expense)

        # Re-read from DB to return fully persisted state
        profile.refresh_from_db()
        cycle.refresh_from_db()

        return Response(
            {
                "expense": ExpenseSerializer(expense).data,
                "profile": FinancialProfileSerializer(profile).data,
                "cycle":   MonthCycleSerializer(cycle).data,
                "alerts":  AlertSerializer(new_alerts, many=True).data,
            },
            status=status.HTTP_201_CREATED,
        )


# ──────────────────────────────────────────────────────────────────────
# 11. Daily Limit  →  GET /api/expenses/daily-limit/
# ──────────────────────────────────────────────────────────────────────

class DailyLimitView(APIView):
    """
    Return the computed daily spending limit for the current active cycle.

    GET  /api/expenses/daily-limit/

    Formula:
        total_days_in_month = days in current month (28-31)
        daily_limit = remaining_budget / total_days_in_month
        
    This provides a flexible daily guideline rather than strict enforcement.
    Users can spend more on some days (groceries, bills) and less on others.
    The daily_limit adjusts as remaining_budget decreases.

    Success 200:
        {
            "daily_limit":     "333.33",
            "remaining_budget":"5000.00",
            "total_days":      30,
            "days_passed":     15,
            "today_spent":     "450.00"
        }

    404 if no active cycle exists.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        cycle = (
            MonthCycle.objects
            .filter(user=request.user, status=MonthCycle.STATUS_ACTIVE)
            .order_by("-year", "-month")
            .first()
        )
        if cycle is None:
            return Response(
                {"detail": "No active cycle. Submit income via POST /api/income/."},
                status=status.HTTP_404_NOT_FOUND,
            )

        today          = timezone.localdate()
        total_days     = calendar.monthrange(today.year, today.month)[1]
        days_passed    = today.day
        
        # Daily limit based on total days in month (flexible guideline)
        daily_limit    = cycle.remaining_budget / Decimal(total_days) if total_days > 0 else Decimal("0.00")

        # Total spent today
        today_spent = (
            Expense.objects
            .filter(cycle=cycle, date=today)
            .values_list("amount", flat=True)
        )
        today_spent = sum(today_spent, Decimal("0.00"))

        return Response(
            {
                "daily_limit":      round(daily_limit, 2),
                "remaining_budget": cycle.remaining_budget,
                "total_days":       total_days,
                "days_passed":      days_passed,
                "today_spent":      today_spent,
            },
            status=status.HTTP_200_OK,
        )


# ──────────────────────────────────────────────────────────────────────
# 12. List Expenses  →  GET /api/expenses/
# ──────────────────────────────────────────────────────────────────────

class ExpenseListView(generics.ListAPIView):
    """
    Return all expenses for the authenticated user's active cycle, newest first.

    GET  /api/expenses/

    Optional query params:
        ?cycle=<id>     filter by a specific cycle id
        ?category=needs filter by category
    """

    serializer_class   = ExpenseSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Expense.objects.filter(user=self.request.user)

        cycle_id = self.request.query_params.get("cycle")
        if cycle_id:
            qs = qs.filter(cycle_id=cycle_id)
        else:
            # Default: active cycle only
            active_cycle = (
                MonthCycle.objects
                .filter(user=self.request.user, status=MonthCycle.STATUS_ACTIVE)
                .order_by("-year", "-month")
                .first()
            )
            if active_cycle:
                qs = qs.filter(cycle=active_cycle)
            else:
                qs = qs.none()

        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category=category)

        return qs


# ──────────────────────────────────────────────────────────────────────
# 13. Alerts  →  GET /api/alerts/
# ──────────────────────────────────────────────────────────────────────

class AlertListView(generics.ListAPIView):
    """
    Return unread alerts for the authenticated user, newest first.

    GET  /api/alerts/

    To include read alerts, pass ?all=true.

    Success 200:
        [ { "id", "type", "message", "is_read", "created_at" }, ... ]
    """

    serializer_class   = AlertSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Alert.objects.filter(user=self.request.user)
        if self.request.query_params.get("all") != "true":
            qs = qs.filter(is_read=False)
        return qs


# ──────────────────────────────────────────────────────────────────────
# 14. Mark Alert Read  →  PATCH /api/alerts/<id>/read/
# ──────────────────────────────────────────────────────────────────────

class AlertMarkReadView(APIView):
    """
    Mark a single alert as read.

    PATCH  /api/alerts/<id>/read/

    Success 200:
        { "id": 1, "is_read": true, ... }

    404 if the alert does not belong to the authenticated user.
    """

    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk: int):
        try:
            alert = Alert.objects.get(pk=pk, user=request.user)
        except Alert.DoesNotExist:
            return Response(
                {"detail": "Alert not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        alert.is_read = True
        alert.save(update_fields=["is_read"])
        return Response(AlertSerializer(alert).data, status=status.HTTP_200_OK)



# ──────────────────────────────────────────────────────────────────────
# 15. Reset Expenses  →  POST /api/cycle/current/reset-expenses/
# ──────────────────────────────────────────────────────────────────────

class ResetExpensesView(APIView):
    """
    Delete all expenses from the current active cycle and restore budgets.
    
    POST  /api/cycle/current/reset-expenses/
    
    This will:
    - Delete all expenses from the current cycle
    - Restore remaining_budget to full amount (expenses_budget + wants_budget)
    - Restore cash_on_hand by adding back all spent amounts
    - Recalculate net worth snapshot
    
    Success 200:
        {
            "message": "Expenses reset successfully",
            "deleted_count": 6,
            "cycle": { ... },
            "profile": { ... }
        }
    
    404 if no active cycle exists.
    """
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        # Get active cycle
        cycle = (
            MonthCycle.objects
            .filter(user=request.user, status=MonthCycle.STATUS_ACTIVE)
            .order_by("-year", "-month")
            .first()
        )
        
        if cycle is None:
            return Response(
                {"error": "No active cycle. Submit income via POST /api/income/ first."},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        profile, _ = FinancialProfile.objects.get_or_create(user=request.user)
        
        # Calculate total spent in this cycle
        expenses = Expense.objects.filter(cycle=cycle)
        total_spent = sum(expense.amount for expense in expenses)
        expense_count = expenses.count()
        
        # Delete all expenses
        expenses.delete()
        
        # Restore remaining_budget to full amount
        cycle.remaining_budget = cycle.expenses_budget + cycle.wants_budget
        cycle.save()
        
        # Restore cash_on_hand
        profile.cash_on_hand += total_spent
        profile.save()
        
        # Capture updated net worth
        NetWorthSnapshot.capture(profile)
        
        return Response(
            {
                "message": "Expenses reset successfully",
                "deleted_count": expense_count,
                "total_restored": total_spent,
                "cycle": MonthCycleSerializer(cycle).data,
                "profile": FinancialProfileSerializer(profile).data,
            },
            status=status.HTTP_200_OK,
        )



# ──────────────────────────────────────────────────────────────────────
# 16. Investments CRUD  →  /api/investments/
# ──────────────────────────────────────────────────────────────────────

class InvestmentListCreateView(generics.ListCreateAPIView):
    """
    List all investments or create a new investment.
    
    GET  /api/investments/
    POST /api/investments/
    
    Request body (POST):
        {
            "name": "BDO Stock",
            "type": "stocks",
            "total_invested": "10000.00",
            "current_value": "12000.00"
        }
    
    When creating an investment, the FinancialProfile.investments_total
    is automatically synced with the sum of all investments.
    """
    
    serializer_class = InvestmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Investment.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        investment = serializer.save(user=self.request.user)
        
        # Sync investments_total in FinancialProfile
        profile, _ = FinancialProfile.objects.get_or_create(user=self.request.user)
        profile.sync_investments_total()
        
        # Capture net worth snapshot
        NetWorthSnapshot.capture(profile)


class InvestmentDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update, or delete a specific investment.
    
    GET    /api/investments/<id>/
    PUT    /api/investments/<id>/
    PATCH  /api/investments/<id>/
    DELETE /api/investments/<id>/
    
    When updating or deleting, the FinancialProfile.investments_total
    is automatically synced.
    """
    
    serializer_class = InvestmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Investment.objects.filter(user=self.request.user)
    
    def perform_update(self, serializer):
        serializer.save()
        
        # Sync investments_total in FinancialProfile
        profile, _ = FinancialProfile.objects.get_or_create(user=self.request.user)
        profile.sync_investments_total()
        
        # Capture net worth snapshot
        NetWorthSnapshot.capture(profile)
    
    def perform_destroy(self, instance):
        user = instance.user
        instance.delete()
        
        # Sync investments_total in FinancialProfile
        profile, _ = FinancialProfile.objects.get_or_create(user=user)
        profile.sync_investments_total()
        
        # Capture net worth snapshot
        NetWorthSnapshot.capture(profile)


# ──────────────────────────────────────────────────────────────────────
# 17. Close Month  →  POST /api/month/close/
# ──────────────────────────────────────────────────────────────────────

class CloseMonthView(APIView):
    """
    End-of-month engine: close current cycle and create summary.
    
    POST  /api/month/close/
    
    Steps 22-25:
        22. Create MonthSummary from current cycle
        23. Move remaining_budget to cash_on_hand (already there)
        24. Move excess cash to savings (optional)
        25. Close cycle (status='closed')
        26. Recalculate net worth snapshot
    
    Success 200:
        {
            "message": "Month closed successfully",
            "summary": { ... },
            "profile": { ... }
        }
    """
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        # Get active cycle
        cycle = (
            MonthCycle.objects
            .filter(user=request.user, status=MonthCycle.STATUS_ACTIVE)
            .order_by("-year", "-month")
            .first()
        )
        
        if cycle is None:
            return Response(
                {"error": "No active cycle to close."},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        profile, _ = FinancialProfile.objects.get_or_create(user=request.user)
        
        # Step 22 — Create MonthSummary
        summary = MonthSummary.create_from_cycle(cycle)
        
        # Step 23 — Remaining budget is already in cash_on_hand
        # (no action needed, it's already there)
        
        # Step 24 — Optional: Move excess cash to savings
        # Get user preference for auto-save threshold (default: keep all in cash)
        auto_save_threshold = request.data.get("auto_save_threshold")
        if auto_save_threshold:
            try:
                threshold = Decimal(str(auto_save_threshold))
                if profile.cash_on_hand > threshold:
                    excess = profile.cash_on_hand - threshold
                    profile.cash_on_hand -= excess
                    profile.savings += excess
                    profile.save()
            except (ValueError, TypeError):
                pass  # Invalid threshold, skip auto-save
        
        # Step 25 — Close the cycle
        cycle.status = MonthCycle.STATUS_CLOSED
        cycle.save()
        
        # Step 26 — Recalculate net worth snapshot
        NetWorthSnapshot.capture(profile)
        
        return Response(
            {
                "message": "Month closed successfully",
                "summary": MonthSummarySerializer(summary).data,
                "profile": FinancialProfileSerializer(profile).data,
            },
            status=status.HTTP_200_OK,
        )


# ──────────────────────────────────────────────────────────────────────
# 18. Reports  →  GET /api/reports/
# ──────────────────────────────────────────────────────────────────────

class ReportsView(APIView):
    """
    Monthly summary history and charts data.
    
    GET  /api/reports/
    
    Query params:
        - months: number of months to include (default: 12)
        - year: filter by specific year (optional)
    
    Success 200:
        {
            "summaries": [ ... ],
            "charts": {
                "income_trend": [ ... ],
                "expense_trend": [ ... ],
                "savings_trend": [ ... ],
                "net_worth_trend": [ ... ]
            },
            "totals": {
                "total_income": "120000.00",
                "total_expenses": "80000.00",
                "total_saved": "40000.00"
            }
        }
    """
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        # Get query parameters
        months = int(request.query_params.get("months", 12))
        year = request.query_params.get("year")
        
        # Build queryset
        summaries_qs = MonthSummary.objects.filter(user=request.user)
        
        if year:
            summaries_qs = summaries_qs.filter(cycle__year=int(year))
        
        summaries_qs = summaries_qs.order_by("-cycle__year", "-cycle__month")[:months]
        summaries = list(summaries_qs)
        
        # Serialize summaries
        summaries_data = MonthSummarySerializer(summaries, many=True).data
        
        # Prepare chart data (reverse order for chronological display)
        summaries_reversed = list(reversed(summaries))
        
        charts = {
            "income_trend": [
                {
                    "month": f"{s.cycle.year}-{s.cycle.month:02d}",
                    "value": float(s.total_income)
                }
                for s in summaries_reversed
            ],
            "expense_trend": [
                {
                    "month": f"{s.cycle.year}-{s.cycle.month:02d}",
                    "value": float(s.total_expenses)
                }
                for s in summaries_reversed
            ],
            "savings_trend": [
                {
                    "month": f"{s.cycle.year}-{s.cycle.month:02d}",
                    "value": float(s.total_saved)
                }
                for s in summaries_reversed
            ],
            "net_worth_trend": [
                {
                    "month": f"{s.cycle.year}-{s.cycle.month:02d}",
                    "value": float(s.net_worth_end)
                }
                for s in summaries_reversed
            ],
        }
        
        # Calculate totals
        totals = {
            "total_income": sum(s.total_income for s in summaries),
            "total_expenses": sum(s.total_expenses for s in summaries),
            "total_saved": sum(s.total_saved for s in summaries),
        }
        
        return Response(
            {
                "summaries": summaries_data,
                "charts": charts,
                "totals": totals,
            },
            status=status.HTTP_200_OK,
        )


