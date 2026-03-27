# api/views.py

from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import FinancialProfile, MonthCycle, NetWorthSnapshot
from .serializers import (
    CustomTokenObtainPairSerializer,
    FinancialProfileSerializer,
    MonthCycleSerializer,
    NetWorthSnapshotSerializer,
    RegisterSerializer,
    UserSerializer,
)
from .services import run_allocation_engine, run_invest


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
             → emergency_fund  (fill to ₱10,000)
             → spendable reserved (₱10,000: ₱7k needs + ₱3k wants)
             → rigs_fund        (up to ₱10,000)
             → savings          (up to ₱20,000)
             → remainder stays in cash_on_hand

    Success 200:
        { "cycle": { ... }, "profile": { ... } }
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        now   = timezone.now()
        year  = int(request.data.get("year",  now.year))
        month = int(request.data.get("month", now.month))

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

        cycle, created = MonthCycle.objects.get_or_create(
            user=request.user,
            year=year,
            month=month,
            defaults={"income": income},
        )

        if not created:
            # Re-running this month: clear prior allocation logs and reset cycle
            cycle.allocation_logs.all().delete()

        # Snapshot BEFORE so we can debug what changed
        ef_before = profile.emergency_fund

        cycle = run_allocation_engine(profile, cycle, income)

        # Always re-read from DB to guarantee the response reflects persisted state
        profile.refresh_from_db()

        print(
            f"[income] EF before={ef_before} | after={profile.emergency_fund} | "
            f"rigs={profile.rigs_fund} | savings={profile.savings} | "
            f"cash={profile.cash_on_hand}"
        )

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
    Return the most recent active MonthCycle.

    Returns 404 if no active cycle exists (user has not submitted income yet).
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
        return Response(
            MonthCycleSerializer(cycle).data,
            status=status.HTTP_200_OK,
        )