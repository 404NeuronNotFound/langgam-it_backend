# api/serializers.py

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import AllocationLog, FinancialProfile, MonthCycle, NetWorthSnapshot, Alert, Expense, Investment, MonthSummary, InvestmentAllocation


# ──────────────────────────────────────────────────────────────────────
# 1. Register
# ──────────────────────────────────────────────────────────────────────

class RegisterSerializer(serializers.ModelSerializer):
    """
    Creates a new User account.

    Validates:
      - username uniqueness (case-insensitive)
      - email uniqueness (case-insensitive)
      - password strength via Django's AUTH_PASSWORD_VALIDATORS
      - password == confirm_password

    Does not return tokens — the caller should POST /api/auth/token/ next.
    """

    confirm_password = serializers.CharField(write_only=True, required=True)
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
    )

    class Meta:
        model  = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "password",
            "confirm_password",
        ]
        extra_kwargs = {
            "first_name": {"required": True},
            "last_name":  {"required": True},
            "email":      {"required": True},
        }

    def validate_email(self, value: str) -> str:
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value.lower()

    def validate_username(self, value: str) -> str:
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("This username is already taken.")
        return value

    def validate(self, attrs: dict) -> dict:
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return attrs

    def create(self, validated_data: dict) -> User:
        validated_data.pop("confirm_password")
        return User.objects.create_user(
            username   = validated_data["username"],
            email      = validated_data["email"],
            password   = validated_data["password"],
            first_name = validated_data.get("first_name", ""),
            last_name  = validated_data.get("last_name", ""),
        )


# ──────────────────────────────────────────────────────────────────────
# 2. Login — custom JWT pair
# ──────────────────────────────────────────────────────────────────────

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Extends the default JWT login response to include basic user info.

    Response shape:
        {
            "access":  "<JWT>",
            "refresh": "<JWT>",
            "user": {
                "id":         1,
                "username":   "juandelacruz",
                "first_name": "Juan",
                "last_name":  "dela Cruz",
                "email":      "juan@example.com"
            }
        }
    """

    def validate(self, attrs: dict) -> dict:
        data = super().validate(attrs)
        data["user"] = {
            "id":         self.user.id,
            "username":   self.user.username,
            "first_name": self.user.first_name,
            "last_name":  self.user.last_name,
            "email":      self.user.email,
        }
        return data


# ──────────────────────────────────────────────────────────────────────
# 3. User — read-only
# ──────────────────────────────────────────────────────────────────────

class UserSerializer(serializers.ModelSerializer):
    """Read-only snapshot of the authenticated user. Used by GET /api/auth/me/."""

    class Meta:
        model        = User
        fields       = ["id", "username", "first_name", "last_name", "email", "date_joined"]
        read_only_fields = fields


# ──────────────────────────────────────────────────────────────────────
# 4. FinancialProfile
# ──────────────────────────────────────────────────────────────────────

class FinancialProfileSerializer(serializers.ModelSerializer):
    """
    Read / partial-update the authenticated user's financial profile.

    net_worth is a read-only computed property on the model.
    All five bucket fields are individually writable via PATCH.
    """

    net_worth = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model  = FinancialProfile
        fields = [
            "id",
            "emergency_fund",
            "savings",
            "rigs_fund",
            "cash_on_hand",
            "investments_total",
            "net_worth",
            "updated_at",
        ]
        read_only_fields = ["id", "net_worth", "updated_at"]


# ──────────────────────────────────────────────────────────────────────
# 5. NetWorthSnapshot — read-only
# ──────────────────────────────────────────────────────────────────────

class NetWorthSnapshotSerializer(serializers.ModelSerializer):
    """
    Read-only historical net-worth snapshot.
    Snapshots are created server-side only — clients cannot POST them directly.
    """

    class Meta:
        model  = NetWorthSnapshot
        fields = [
            "id",
            "emergency_fund",
            "savings",
            "rigs_fund",
            "cash_on_hand",
            "investments_total",
            "net_worth",
            "captured_at",
        ]
        read_only_fields = fields


# ──────────────────────────────────────────────────────────────────────
# 6. AllocationLog — read-only
# ──────────────────────────────────────────────────────────────────────

class AllocationLogSerializer(serializers.ModelSerializer):
    """Read-only ledger entry for a single fund transfer within a MonthCycle."""

    class Meta:
        model  = AllocationLog
        fields = ["id", "from_bucket", "to_bucket", "amount", "timestamp"]
        read_only_fields = fields


# ──────────────────────────────────────────────────────────────────────
# 7. MonthCycle — read-only (mutations happen via the allocation engine)
# ──────────────────────────────────────────────────────────────────────

class MonthCycleSerializer(serializers.ModelSerializer):
    """
    Full representation of a MonthCycle including its allocation log entries.
    Cycles are created and mutated by the allocation engine, never directly
    by the client.
    """

    allocation_logs = AllocationLogSerializer(many=True, read_only=True)

    class Meta:
        model  = MonthCycle
        fields = [
            "id",
            "year",
            "month",
            "income",
            # ── What was allocated into each fund ──
            "emergency_fund_budget",
            "rigs_fund_budget",
            "savings_budget",
            # ── Spendable budgets ──
            "expenses_budget",
            "wants_budget",
            "remaining_budget",
            "status",
            "created_at",
            "allocation_logs",
        ]
        read_only_fields = fields

class ExpenseSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and reading expense records.
    
    Write fields (POST):
        - amount: required, decimal
        - category: required, "needs" or "wants"
        - description: optional, string
        - date: optional, defaults to today
    
    Read-only fields:
        - id, cycle, created_at (set by server)
    """
    
    class Meta:
        model = Expense
        fields = [
            "id",
            "cycle",
            "amount",
            "category",
            "description",
            "date",
            "created_at",
        ]
        read_only_fields = ["id", "cycle", "created_at"]
        extra_kwargs = {
            "date": {"required": False},
            "description": {"required": False, "allow_blank": True},
        }

class AlertSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(source="get_type_display", read_only=True)

    class Meta:
        model = Alert
        fields = [
            "id",
            "type",
            "type_display",
            "message",
            "is_read",
            "created_at",
        ]

class InvestmentSerializer(serializers.ModelSerializer):
    """
    Serializer for Investment model with computed profit/loss fields.
    
    Read-only computed fields:
        - profit_loss: current_value - total_invested
        - profit_loss_percentage: (profit_loss / total_invested) * 100
    """
    
    profit_loss = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )
    
    profit_loss_percentage = serializers.DecimalField(
        max_digits=8,
        decimal_places=2,
        read_only=True,
    )
    
    class Meta:
        model = Investment
        fields = [
            "id",
            "name",
            "type",
            "total_invested",
            "current_value",
            "profit_loss",
            "profit_loss_percentage",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "profit_loss", "profit_loss_percentage", "created_at", "updated_at"]


class MonthSummarySerializer(serializers.ModelSerializer):
    """
    Serializer for MonthSummary model with computed net worth change.
    
    Includes cycle details and computed fields for financial overview.
    """
    
    net_worth_change = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )
    
    # Include basic cycle info
    cycle_year = serializers.IntegerField(source="cycle.year", read_only=True)
    cycle_month = serializers.IntegerField(source="cycle.month", read_only=True)
    
    class Meta:
        model = MonthSummary
        fields = [
            "id",
            "cycle",
            "cycle_year",
            "cycle_month",
            "total_income",
            "total_expenses",
            "total_saved",
            "remaining_carried_over",
            "net_worth_start",
            "net_worth_end",
            "net_worth_change",
            "created_at",
        ]
        read_only_fields = fields  # All fields are read-only (generated from cycle data)


class InvestmentAllocationSerializer(serializers.ModelSerializer):
    """
    Serializer for InvestmentAllocation model.
    
    Shows how the user's total investments are allocated across individual investments.
    Includes computed profit/loss fields.
    """
    
    profit_loss_percentage = serializers.SerializerMethodField()
    
    class Meta:
        model = InvestmentAllocation
        fields = [
            "total_allocated",
            "total_current_value",
            "total_profit_loss",
            "profit_loss_percentage",
            "updated_at",
        ]
        read_only_fields = fields
    
    def get_profit_loss_percentage(self, obj) -> Decimal:
        """Calculate profit/loss as percentage."""
        if obj.total_allocated == Decimal("0.00"):
            return Decimal("0.00")
        return (obj.total_profit_loss / obj.total_allocated) * Decimal("100.00")
