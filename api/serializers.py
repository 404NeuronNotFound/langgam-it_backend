from decimal import Decimal
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
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


TWO_PLACES = Decimal("0.01")
ONE_PLACE = Decimal("0.1")


def valid_choice_message(field_name: str, choices: list[str]) -> str:
    return f"Invalid {field_name}. Valid choices are: {', '.join(choices)}."


# ── 1. RegisterSerializer ──
class RegisterSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField()
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "password",
            "confirm_password",
        ]

    def validate_email(self, value: str) -> str:
        email = value.lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return email

    def validate_username(self, value: str) -> str:
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value

    def validate(self, attrs: dict) -> dict:
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match."}
            )
        return attrs

    def create(self, validated_data: dict) -> User:
        validated_data.pop("confirm_password")
        return User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
        )


# ── 2. CustomTokenObtainPairSerializer ──
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs: dict) -> dict:
        data = super().validate(attrs)
        data["user"] = {
            "id": self.user.id,
            "username": self.user.username,
            "first_name": self.user.first_name,
            "last_name": self.user.last_name,
            "email": self.user.email,
        }
        return data


# ── 3. UserSerializer ──
class UserSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    first_name = serializers.CharField(read_only=True)
    last_name = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)
    date_joined = serializers.DateTimeField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "date_joined"]


# ── 4. FinancialAccountSerializer ──
class FinancialAccountSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = FinancialAccount
        fields = ["id", "name", "created_at"]


# ── 5. FundSerializer ──
class FundSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)
    type = serializers.CharField()
    status = serializers.CharField()
    current_balance = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )
    created_at = serializers.DateTimeField(read_only=True)
    monthly_allocation_needed = serializers.SerializerMethodField()
    progress_percentage = serializers.SerializerMethodField()

    class Meta:
        model = Fund
        fields = [
            "id",
            "name",
            "type",
            "icon",
            "color",
            "current_balance",
            "monthly_allocation",
            "allocation_priority",
            "skip_on_low_income",
            "target_amount",
            "target_date",
            "status",
            "created_at",
            "monthly_allocation_needed",
            "progress_percentage",
        ]

    def get_monthly_allocation_needed(self, obj: Fund) -> Decimal | None:
        if not obj.target_amount or not obj.target_date or obj.status != Fund.STATUS_ACTIVE:
            return None

        today = date.today()
        diff = relativedelta(obj.target_date, today)
        months_left = (diff.years * 12) + diff.months
        if diff.days > 0:
            months_left += 1
        months_left = max(1, months_left)

        needed = (obj.target_amount - obj.current_balance) / Decimal(months_left)
        return max(Decimal("0.00"), needed).quantize(TWO_PLACES)

    def get_progress_percentage(self, obj: Fund) -> Decimal | None:
        if obj.target_amount and obj.target_amount > Decimal("0.00"):
            progress = (obj.current_balance / obj.target_amount) * Decimal("100")
            return min(Decimal("100.0"), progress).quantize(ONE_PLACE)
        return None

    def validate_type(self, value: str) -> str:
        valid_types = [choice[0] for choice in Fund.TYPE_CHOICES]
        if value not in valid_types:
            raise serializers.ValidationError(valid_choice_message("type", valid_types))
        return value

    def validate_status(self, value: str) -> str:
        valid_statuses = [choice[0] for choice in Fund.STATUS_CHOICES]
        if value not in valid_statuses:
            raise serializers.ValidationError(
                valid_choice_message("status", valid_statuses)
            )
        return value


# ── 6. FundCreateSerializer ──
class FundCreateSerializer(serializers.ModelSerializer):
    type = serializers.CharField(required=False, default=Fund.TYPE_GOAL)

    class Meta:
        model = Fund
        fields = [
            "name",
            "type",
            "icon",
            "color",
            "monthly_allocation",
            "allocation_priority",
            "skip_on_low_income",
            "target_amount",
            "target_date",
        ]

    def validate(self, attrs: dict) -> dict:
        fund_type = attrs.get("type", Fund.TYPE_GOAL)
        valid_types = [choice[0] for choice in Fund.TYPE_CHOICES]
        if fund_type not in valid_types:
            raise serializers.ValidationError(
                {"type": valid_choice_message("type", valid_types)}
            )
        if fund_type == Fund.TYPE_SYSTEM:
            raise serializers.ValidationError(
                {"type": "System funds are created only by the system."}
            )
        return attrs

    def validate_target_date(self, value):
        if value and value <= date.today():
            raise serializers.ValidationError("Target date must be in the future.")
        return value


# ── 7. MonthlyBudgetSetupSerializer ──
class MonthlyBudgetSetupSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    total_allocated = serializers.SerializerMethodField()
    allocation_warning = serializers.SerializerMethodField()

    class Meta:
        model = MonthlyBudgetSetup
        fields = [
            "id",
            "estimated_monthly_income",
            "needs_budget",
            "wants_budget",
            "effective_from",
            "created_at",
            "total_allocated",
            "allocation_warning",
        ]

    def get_total_allocated(self, obj: MonthlyBudgetSetup) -> Decimal:
        account = self.context.get("account")
        if not account:
            return Decimal("0.00")
        total = Decimal("0.00")
        for fund in Fund.objects.filter(account=account, status=Fund.STATUS_ACTIVE):
            total += fund.monthly_allocation
        return total

    def get_allocation_warning(self, obj: MonthlyBudgetSetup) -> str | None:
        if self.get_total_allocated(obj) > obj.estimated_monthly_income:
            return "Total fund allocations exceed estimated income."
        return None

    def validate_effective_from(self, value):
        if self.instance is None and value < date.today():
            raise serializers.ValidationError("Effective from cannot be in the past.")
        return value


# ── 8. MonthCycleSerializer ──
class MonthCycleSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)
    year = serializers.IntegerField(read_only=True)
    month = serializers.IntegerField(read_only=True)
    income_entered = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )
    income_scenario = serializers.CharField(read_only=True)
    needs_budget_used = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )
    wants_budget_used = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )
    needs_spent = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    wants_spent = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    remaining_budget = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )
    status = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    needs_remaining = serializers.SerializerMethodField()
    wants_remaining = serializers.SerializerMethodField()
    total_spent = serializers.SerializerMethodField()

    class Meta:
        model = MonthCycle
        fields = [
            "id",
            "year",
            "month",
            "income_entered",
            "income_scenario",
            "needs_budget_used",
            "wants_budget_used",
            "needs_spent",
            "wants_spent",
            "remaining_budget",
            "status",
            "created_at",
            "needs_remaining",
            "wants_remaining",
            "total_spent",
        ]

    def get_needs_remaining(self, obj: MonthCycle) -> Decimal:
        return obj.needs_budget_used - obj.needs_spent

    def get_wants_remaining(self, obj: MonthCycle) -> Decimal:
        return obj.wants_budget_used - obj.wants_spent

    def get_total_spent(self, obj: MonthCycle) -> Decimal:
        return obj.needs_spent + obj.wants_spent


# ── 9. TransferSerializer ──
class TransferSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)
    transfer_type = serializers.CharField()
    from_fund_id = serializers.PrimaryKeyRelatedField(
        source="from_fund",
        queryset=Fund.objects.all(),
        required=False,
        allow_null=True,
    )
    to_fund_id = serializers.PrimaryKeyRelatedField(
        source="to_fund",
        queryset=Fund.objects.all(),
        required=False,
        allow_null=True,
    )
    from_fund_name = serializers.SerializerMethodField()
    to_fund_name = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Transfer
        fields = [
            "id",
            "from_fund_id",
            "to_fund_id",
            "from_fund_name",
            "to_fund_name",
            "amount",
            "transfer_type",
            "note",
            "date",
            "created_at",
        ]

    def get_from_fund_name(self, obj: Transfer) -> str:
        return obj.from_fund.name if obj.from_fund else "External"

    def get_to_fund_name(self, obj: Transfer) -> str:
        return obj.to_fund.name if obj.to_fund else "External"

    def validate_transfer_type(self, value: str) -> str:
        valid_types = [choice[0] for choice in Transfer.TYPE_CHOICES]
        if value not in valid_types:
            raise serializers.ValidationError(valid_choice_message("transfer_type", valid_types))
        return value


# ── 10. TransferCreateSerializer ──
class TransferCreateSerializer(serializers.ModelSerializer):
    transfer_type = serializers.CharField()
    from_fund_id = serializers.PrimaryKeyRelatedField(
        source="from_fund",
        queryset=Fund.objects.all(),
        required=False,
        allow_null=True,
    )
    to_fund_id = serializers.PrimaryKeyRelatedField(
        source="to_fund",
        queryset=Fund.objects.all(),
        required=False,
        allow_null=True,
    )
    date = serializers.DateField(required=False, default=date.today)

    class Meta:
        model = Transfer
        fields = ["from_fund_id", "to_fund_id", "amount", "transfer_type", "note", "date"]

    def validate_amount(self, value: Decimal) -> Decimal:
        if value <= Decimal("0.00"):
            raise serializers.ValidationError("Amount must be greater than 0.")
        return value

    def validate_transfer_type(self, value: str) -> str:
        valid_types = [choice[0] for choice in Transfer.TYPE_CHOICES]
        if value not in valid_types:
            raise serializers.ValidationError(valid_choice_message("transfer_type", valid_types))
        return value

    def validate(self, attrs: dict) -> dict:
        from_fund = attrs.get("from_fund")
        to_fund = attrs.get("to_fund")
        transfer_type = attrs.get("transfer_type")
        amount = attrs.get("amount", Decimal("0.00"))
        note = attrs.get("note", "")

        if from_fund and to_fund and from_fund == to_fund:
            raise serializers.ValidationError(
                {"to_fund_id": "from_fund_id and to_fund_id cannot be the same fund."}
            )

        note_required_types = [
            Transfer.TYPE_FUND_TO_CASH,
            Transfer.TYPE_EXTERNAL_ADD,
            Transfer.TYPE_GOAL_COMPLETED,
        ]
        if transfer_type in note_required_types and not note.strip():
            raise serializers.ValidationError(
                {"note": f"Note is required for {transfer_type} transfers."}
            )

        balance_checked_types = [
            Transfer.TYPE_FUND_TO_CASH,
            Transfer.TYPE_FUND_TO_FUND,
            Transfer.TYPE_CASH_TO_FUND,
        ]
        if (
            transfer_type in balance_checked_types
            and from_fund
            and from_fund.current_balance < amount
        ):
            raise serializers.ValidationError(
                {"amount": "Insufficient balance in the source fund."}
            )

        return attrs


# ── 11. ExpenseSerializer ──
class ExpenseSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)
    category = serializers.CharField()
    date = serializers.DateField(required=False, default=date.today)
    created_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Expense
        fields = ["id", "amount", "category", "description", "date", "created_at"]

    def validate_amount(self, value: Decimal) -> Decimal:
        if value <= Decimal("0.00"):
            raise serializers.ValidationError("Amount must be greater than 0.")
        return value

    def validate_category(self, value: str) -> str:
        valid_categories = [choice[0] for choice in Expense.CATEGORY_CHOICES]
        if value not in valid_categories:
            raise serializers.ValidationError(
                valid_choice_message("category", valid_categories)
            )
        return value


# ── 12. AlertSerializer ──
class AlertSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)
    type = serializers.CharField(read_only=True)
    type_display = serializers.SerializerMethodField()
    message = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Alert
        fields = ["id", "type", "type_display", "message", "is_read", "created_at"]

    def get_type_display(self, obj: Alert) -> str:
        return obj.get_type_display()


# ── 13. NetWorthSnapshotSerializer ──
class NetWorthSnapshotSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)
    net_worth = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    snapshot_data = serializers.JSONField(read_only=True)
    captured_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = NetWorthSnapshot
        fields = ["id", "net_worth", "snapshot_data", "captured_at"]


# ── 14. MonthSummarySerializer ──
class MonthSummarySerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)
    cycle_id = serializers.IntegerField(read_only=True)
    cycle_year = serializers.IntegerField(source="cycle.year", read_only=True)
    cycle_month = serializers.IntegerField(source="cycle.month", read_only=True)
    total_income = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )
    total_needs_spent = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )
    total_wants_spent = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )
    total_allocated_to_funds = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )
    net_worth_start = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )
    net_worth_end = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )
    net_worth_change = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = MonthSummary
        fields = [
            "id",
            "cycle_id",
            "cycle_year",
            "cycle_month",
            "total_income",
            "total_needs_spent",
            "total_wants_spent",
            "total_allocated_to_funds",
            "net_worth_start",
            "net_worth_end",
            "net_worth_change",
            "created_at",
        ]

    def get_net_worth_change(self, obj: MonthSummary) -> Decimal:
        return obj.net_worth_change
