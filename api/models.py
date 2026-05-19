from decimal import Decimal

from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import Max, Sum
from django.utils import timezone


# Accounts
class FinancialAccount(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="financial_account",
    )
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Financial Account"
        verbose_name_plural = "Financial Accounts"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"FinancialAccount({self.user.username}, {self.name})"

    @property
    def net_worth(self) -> Decimal:
        return (
            Fund.objects.filter(account=self, status=Fund.STATUS_ACTIVE).aggregate(
                total=Sum("current_balance")
            )["total"]
            or Decimal("0.00")
        )

    @property
    def cash_on_hand_fund(self) -> "Fund | None":
        return self.funds.filter(name=Fund.SYSTEM_CASH_ON_HAND).first()

    @property
    def emergency_fund(self) -> "Fund | None":
        return self.funds.filter(name=Fund.SYSTEM_EMERGENCY_FUND).first()

    @classmethod
    def create_default_funds(cls, account: "FinancialAccount") -> list["Fund"]:
        defaults = [
            {
                "name": Fund.SYSTEM_EMERGENCY_FUND,
                "type": Fund.TYPE_SYSTEM,
                "allocation_priority": 1,
                "skip_on_low_income": False,
            },
            {
                "name": Fund.SYSTEM_SAVINGS,
                "type": Fund.TYPE_SYSTEM,
                "allocation_priority": 2,
                "skip_on_low_income": False,
            },
            {
                "name": Fund.SYSTEM_CASH_ON_HAND,
                "type": Fund.TYPE_SYSTEM,
                "allocation_priority": 3,
                "skip_on_low_income": False,
            },
        ]
        funds = []
        for data in defaults:
            fund, _ = Fund.objects.get_or_create(
                account=account,
                name=data["name"],
                defaults=data,
            )
            funds.append(fund)
        return funds

    def create_month_cycle(
        self,
        year: int,
        month: int,
        budget_setup: "MonthlyBudgetSetup | None" = None,
    ) -> "MonthCycle":
        return MonthCycle.objects.create(
            account=self,
            budget_setup=budget_setup or MonthlyBudgetSetup.get_active(self),
            year=year,
            month=month,
        )

    @transaction.atomic
    def financial_reset(self) -> None:
        self.funds.update(current_balance=Decimal("0.00"))
        self.month_cycles.all().delete()
        self.transfers.all().delete()
        self.expenses.all().delete()
        NetWorthSnapshot.capture(self)


# Funds
class Fund(models.Model):
    TYPE_SYSTEM = "system_required"
    TYPE_GOAL = "goal"
    TYPE_CHOICES = [
        (TYPE_SYSTEM, "System Required"),
        (TYPE_GOAL, "Goal"),
    ]

    STATUS_ACTIVE = "active"
    STATUS_COMPLETED = "completed"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CLOSED, "Closed"),
    ]

    SYSTEM_EMERGENCY_FUND = "Emergency Fund"
    SYSTEM_SAVINGS = "Savings"
    SYSTEM_CASH_ON_HAND = "Cash on Hand"

    account = models.ForeignKey(
        FinancialAccount,
        on_delete=models.CASCADE,
        related_name="funds",
    )
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    icon = models.CharField(max_length=50, blank=True)
    color = models.CharField(max_length=20, blank=True)
    current_balance = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    monthly_allocation = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    allocation_priority = models.PositiveIntegerField(default=999)
    skip_on_low_income = models.BooleanField(default=False)
    target_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    target_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Fund"
        verbose_name_plural = "Funds"
        ordering = ["allocation_priority", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["account", "name"],
                name="unique_account_fund_name",
            )
        ]

    def __str__(self) -> str:
        return f"Fund({self.account.name}, {self.name}, {self.status})"

    @property
    def is_cash_on_hand(self) -> bool:
        return self.name == self.SYSTEM_CASH_ON_HAND

    @property
    def is_emergency_fund(self) -> bool:
        return self.name == self.SYSTEM_EMERGENCY_FUND

    @property
    def target_progress(self) -> Decimal:
        if not self.target_amount:
            return Decimal("0.00")
        return (self.current_balance / self.target_amount) * Decimal("100.00")

    def save(self, *args, **kwargs) -> None:
        should_capture_snapshot = False
        if (
            self._state.adding
            and self.type == self.TYPE_GOAL
            and self.allocation_priority == 999
        ):
            max_priority = (
                Fund.objects.filter(account=self.account).aggregate(
                    max_priority=Max("allocation_priority")
                )["max_priority"]
                or 3
            )
            self.allocation_priority = max(max_priority + 1, 4)
            if self.skip_on_low_income is False:
                self.skip_on_low_income = True
        elif not self._state.adding and not getattr(self, "_skip_snapshot", False):
            update_fields = kwargs.get("update_fields")
            if update_fields is None or "current_balance" in update_fields:
                old_balance = (
                    Fund.objects.filter(pk=self.pk).values_list(
                        "current_balance", flat=True
                    ).first()
                )
                should_capture_snapshot = old_balance != self.current_balance
        super().save(*args, **kwargs)
        if should_capture_snapshot:
            NetWorthSnapshot.capture(self.account)

    def adjust_balance(self, amount: Decimal, capture_snapshot: bool = True) -> None:
        self.current_balance += amount
        self.save(update_fields=["current_balance"])
        if capture_snapshot:
            NetWorthSnapshot.capture(self.account)

    def close(self, note: str = "") -> None:
        self.current_balance = Decimal("0.00")
        self.status = self.STATUS_CLOSED
        self.save(update_fields=["current_balance", "status"])
        NetWorthSnapshot.capture(self.account)


# Budget setup
class MonthlyBudgetSetup(models.Model):
    account = models.ForeignKey(
        FinancialAccount,
        on_delete=models.CASCADE,
        related_name="budget_setups",
    )
    estimated_monthly_income = models.DecimalField(max_digits=14, decimal_places=2)
    needs_budget = models.DecimalField(max_digits=14, decimal_places=2)
    wants_budget = models.DecimalField(max_digits=14, decimal_places=2)
    effective_from = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Monthly Budget Setup"
        verbose_name_plural = "Monthly Budget Setups"
        ordering = ["-effective_from", "-created_at"]

    def __str__(self) -> str:
        return f"MonthlyBudgetSetup({self.account.name}, {self.effective_from})"

    @classmethod
    def get_active(cls, account: FinancialAccount) -> "MonthlyBudgetSetup | None":
        return (
            cls.objects.filter(account=account, effective_from__lte=timezone.localdate())
            .order_by("-effective_from", "-created_at")
            .first()
        )


# Month cycles
class MonthCycle(models.Model):
    SCENARIO_FULL = "full"
    SCENARIO_LOW = "low"
    SCENARIO_ZERO = "zero"
    SCENARIO_CHOICES = [
        (SCENARIO_FULL, "Full"),
        (SCENARIO_LOW, "Low"),
        (SCENARIO_ZERO, "Zero"),
    ]

    STATUS_ACTIVE = "active"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_CLOSED, "Closed"),
    ]

    account = models.ForeignKey(
        FinancialAccount,
        on_delete=models.CASCADE,
        related_name="month_cycles",
    )
    budget_setup = models.ForeignKey(
        MonthlyBudgetSetup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="month_cycles",
    )
    year = models.PositiveIntegerField()
    month = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    income_entered = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    income_scenario = models.CharField(
        max_length=10,
        choices=SCENARIO_CHOICES,
        blank=True,
    )
    needs_budget_used = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    wants_budget_used = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    needs_spent = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    wants_spent = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    remaining_budget = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Month Cycle"
        verbose_name_plural = "Month Cycles"
        ordering = ["-year", "-month"]
        constraints = [
            models.UniqueConstraint(
                fields=["account", "year", "month"],
                name="unique_account_year_month",
            )
        ]

    def __str__(self) -> str:
        return f"MonthCycle({self.account.name}, {self.year}-{self.month:02d})"

    @property
    def total_spent(self) -> Decimal:
        return self.needs_spent + self.wants_spent

    def classify_income(self, amount: Decimal) -> str:
        estimated = (
            self.budget_setup.estimated_monthly_income
            if self.budget_setup
            else Decimal("0.00")
        )
        if amount == Decimal("0.00"):
            return self.SCENARIO_ZERO
        if amount < estimated:
            return self.SCENARIO_LOW
        return self.SCENARIO_FULL

    @transaction.atomic
    def enter_income(self, amount: Decimal, date=None) -> Decimal:
        date = date or timezone.localdate()
        remaining_income = amount
        scenario = self.classify_income(amount)

        self.income_entered = amount
        self.income_scenario = scenario
        if self.budget_setup:
            self.needs_budget_used = self.budget_setup.needs_budget
            self.wants_budget_used = self.budget_setup.wants_budget
            self.remaining_budget = (
                self.budget_setup.needs_budget + self.budget_setup.wants_budget
            )
        self.save(
            update_fields=[
                "income_entered",
                "income_scenario",
                "needs_budget_used",
                "wants_budget_used",
                "remaining_budget",
            ]
        )

        if scenario != self.SCENARIO_ZERO:
            for fund in self.account.funds.filter(status=Fund.STATUS_ACTIVE).order_by(
                "allocation_priority", "created_at"
            ):
                if scenario == self.SCENARIO_LOW and fund.skip_on_low_income:
                    continue
                if remaining_income <= Decimal("0.00"):
                    break
                transfer_amount = min(fund.monthly_allocation, remaining_income)
                if transfer_amount <= Decimal("0.00"):
                    continue
                Transfer.objects.create(
                    account=self.account,
                    cycle=self,
                    to_fund=fund,
                    amount=transfer_amount,
                    transfer_type=Transfer.TYPE_INCOME_ALLOCATION,
                    date=date,
                )
                remaining_income -= transfer_amount

            cash_fund = self.account.cash_on_hand_fund
            if cash_fund and remaining_income > Decimal("0.00"):
                Transfer.objects.create(
                    account=self.account,
                    cycle=self,
                    to_fund=cash_fund,
                    amount=remaining_income,
                    transfer_type=Transfer.TYPE_MONTH_END_CARRY,
                    date=date,
                )

        NetWorthSnapshot.capture(self.account)
        return remaining_income

    @transaction.atomic
    def draw_survival_from_emergency(self, date=None) -> "Transfer | None":
        if not self.budget_setup:
            return None
        emergency_fund = self.account.emergency_fund
        cash_fund = self.account.cash_on_hand_fund
        if not emergency_fund or not cash_fund:
            return None
        return Transfer.objects.create(
            account=self.account,
            cycle=self,
            from_fund=emergency_fund,
            to_fund=cash_fund,
            amount=self.budget_setup.needs_budget,
            transfer_type=Transfer.TYPE_SURVIVAL_DRAW,
            note="Emergency fund draw for zero-income month",
            date=date or timezone.localdate(),
        )

    @transaction.atomic
    def close(self) -> "MonthSummary":
        self.status = self.STATUS_CLOSED
        self.save(update_fields=["status"])
        snapshot = NetWorthSnapshot.capture(self.account)
        summary, _ = MonthSummary.objects.update_or_create(
            account=self.account,
            cycle=self,
            defaults={
                "total_income": self.income_entered,
                "total_needs_spent": self.needs_spent,
                "total_wants_spent": self.wants_spent,
                "total_allocated_to_funds": self.transfers.filter(
                    transfer_type=Transfer.TYPE_INCOME_ALLOCATION
                ).aggregate(total=Sum("amount"))["total"]
                or Decimal("0.00"),
                "net_worth_end": snapshot.net_worth,
            },
        )
        return summary


# Transfers
class Transfer(models.Model):
    TYPE_INCOME_ALLOCATION = "income_allocation"
    TYPE_FUND_TO_CASH = "fund_to_cash"
    TYPE_CASH_TO_FUND = "cash_to_fund"
    TYPE_FUND_TO_FUND = "fund_to_fund"
    TYPE_EXTERNAL_ADD = "external_add"
    TYPE_GOAL_COMPLETED = "goal_completed"
    TYPE_SURVIVAL_DRAW = "survival_draw"
    TYPE_MONTH_END_CARRY = "month_end_carry"
    TYPE_CHOICES = [
        (TYPE_INCOME_ALLOCATION, "Income Allocation"),
        (TYPE_FUND_TO_CASH, "Fund to Cash"),
        (TYPE_CASH_TO_FUND, "Cash to Fund"),
        (TYPE_FUND_TO_FUND, "Fund to Fund"),
        (TYPE_EXTERNAL_ADD, "External Add"),
        (TYPE_GOAL_COMPLETED, "Goal Completed"),
        (TYPE_SURVIVAL_DRAW, "Survival Draw"),
        (TYPE_MONTH_END_CARRY, "Month End Carry"),
    ]

    account = models.ForeignKey(
        FinancialAccount,
        on_delete=models.CASCADE,
        related_name="transfers",
    )
    cycle = models.ForeignKey(
        MonthCycle,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transfers",
    )
    from_fund = models.ForeignKey(
        Fund,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transfers_out",
    )
    to_fund = models.ForeignKey(
        Fund,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transfers_in",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    transfer_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    note = models.TextField(blank=True, default="")
    date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Transfer"
        verbose_name_plural = "Transfers"
        ordering = ["-date", "-created_at"]

    def __str__(self) -> str:
        source = self.from_fund.name if self.from_fund else "External"
        target = self.to_fund.name if self.to_fund else "External"
        return f"Transfer({source} -> {target}, {self.amount})"

    def save(self, *args, **kwargs) -> None:
        is_create = self._state.adding
        with transaction.atomic():
            super().save(*args, **kwargs)
            if is_create and not getattr(self, "_skip_balance_apply", False):
                self.apply()
                NetWorthSnapshot.capture(self.account)

    def apply(self) -> None:
        if self.from_fund:
            self.from_fund.current_balance -= self.amount
            self.from_fund._skip_snapshot = True
            self.from_fund.save(update_fields=["current_balance"])
        if self.to_fund:
            self.to_fund.current_balance += self.amount
            self.to_fund._skip_snapshot = True
            self.to_fund.save(update_fields=["current_balance"])
        if self.transfer_type == self.TYPE_GOAL_COMPLETED and self.from_fund:
            self.from_fund.current_balance = Decimal("0.00")
            self.from_fund.status = Fund.STATUS_COMPLETED
            self.from_fund._skip_snapshot = True
            self.from_fund.save(update_fields=["current_balance", "status"])


# Expenses
class Expense(models.Model):
    CATEGORY_NEEDS = "needs"
    CATEGORY_WANTS = "wants"
    CATEGORY_CHOICES = [
        (CATEGORY_NEEDS, "Needs"),
        (CATEGORY_WANTS, "Wants"),
    ]

    account = models.ForeignKey(
        FinancialAccount,
        on_delete=models.CASCADE,
        related_name="expenses",
    )
    cycle = models.ForeignKey(
        MonthCycle,
        on_delete=models.CASCADE,
        related_name="expenses",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    category = models.CharField(max_length=10, choices=CATEGORY_CHOICES)
    description = models.CharField(max_length=255, blank=True, default="")
    date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Expense"
        verbose_name_plural = "Expenses"
        ordering = ["-date", "-created_at"]

    def __str__(self) -> str:
        return f"Expense({self.account.name}, {self.category}, {self.amount})"

    def save(self, *args, **kwargs) -> None:
        is_create = self._state.adding
        with transaction.atomic():
            super().save(*args, **kwargs)
            if is_create and getattr(self, "_apply_on_save", False):
                self.apply()
                self.run_monitoring()
                NetWorthSnapshot.capture(self.account)

    def apply(self) -> None:
        cash_fund = self.account.cash_on_hand_fund
        if cash_fund:
            cash_fund.current_balance -= self.amount
            cash_fund._skip_snapshot = True
            cash_fund.save(update_fields=["current_balance"])

        if self.category == self.CATEGORY_NEEDS:
            self.cycle.needs_spent += self.amount
        if self.category == self.CATEGORY_WANTS:
            self.cycle.wants_spent += self.amount
        self.cycle.remaining_budget -= self.amount
        self.cycle.save(
            update_fields=["needs_spent", "wants_spent", "remaining_budget"]
        )

    def run_monitoring(self) -> None:
        if self.cycle.remaining_budget < Decimal("0.00"):
            Alert.objects.create(
                account=self.account,
                cycle=self.cycle,
                type=Alert.TYPE_OVERSPEND,
                message="Monthly budget has been exceeded.",
            )
        if self.cycle.remaining_budget <= Decimal("0.00"):
            Alert.objects.create(
                account=self.account,
                cycle=self.cycle,
                type=Alert.TYPE_HARD_STOP,
                message="Remaining budget is depleted.",
            )

        emergency_fund = self.account.emergency_fund
        if emergency_fund and emergency_fund.current_balance < Decimal("10000.00"):
            Alert.objects.create(
                account=self.account,
                cycle=self.cycle,
                type=Alert.TYPE_EMERGENCY_LOW,
                message="Emergency fund is below the recommended minimum.",
            )


# Alerts
class Alert(models.Model):
    TYPE_OVERSPEND = "overspend"
    TYPE_DAILY_LIMIT = "daily_limit"
    TYPE_HARD_STOP = "hard_stop"
    TYPE_EMERGENCY_LOW = "emergency_low"
    TYPE_GOAL_BEHIND = "goal_behind"
    TYPE_CHOICES = [
        (TYPE_OVERSPEND, "Overspend"),
        (TYPE_DAILY_LIMIT, "Daily Limit"),
        (TYPE_HARD_STOP, "Hard Stop"),
        (TYPE_EMERGENCY_LOW, "Emergency Low"),
        (TYPE_GOAL_BEHIND, "Goal Behind"),
    ]

    account = models.ForeignKey(
        FinancialAccount,
        on_delete=models.CASCADE,
        related_name="alerts",
    )
    cycle = models.ForeignKey(
        MonthCycle,
        on_delete=models.CASCADE,
        related_name="alerts",
    )
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Alert"
        verbose_name_plural = "Alerts"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Alert({self.account.name}, {self.type}, read={self.is_read})"


# Net worth snapshots
class NetWorthSnapshot(models.Model):
    account = models.ForeignKey(
        FinancialAccount,
        on_delete=models.CASCADE,
        related_name="net_worth_snapshots",
    )
    net_worth = models.DecimalField(max_digits=14, decimal_places=2)
    snapshot_data = models.JSONField()
    captured_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Net Worth Snapshot"
        verbose_name_plural = "Net Worth Snapshots"
        ordering = ["-captured_at"]

    def __str__(self) -> str:
        return f"NetWorthSnapshot({self.account.name}, {self.net_worth})"

    @classmethod
    def capture(cls, account: FinancialAccount) -> "NetWorthSnapshot":
        funds = Fund.objects.filter(account=account, status=Fund.STATUS_ACTIVE)
        snapshot_data = {str(fund.id): str(fund.current_balance) for fund in funds}
        net_worth = sum(
            (fund.current_balance for fund in funds),
            Decimal("0.00"),
        )
        return cls.objects.create(
            account=account,
            net_worth=net_worth,
            snapshot_data=snapshot_data,
        )


# Month summaries
class MonthSummary(models.Model):
    account = models.ForeignKey(
        FinancialAccount,
        on_delete=models.CASCADE,
        related_name="month_summaries",
    )
    cycle = models.OneToOneField(
        MonthCycle,
        on_delete=models.CASCADE,
        related_name="summary",
    )
    total_income = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    total_needs_spent = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    total_wants_spent = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    total_allocated_to_funds = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    net_worth_start = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    net_worth_end = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Month Summary"
        verbose_name_plural = "Month Summaries"
        ordering = ["-cycle__year", "-cycle__month"]
        constraints = [
            models.UniqueConstraint(
                fields=["account", "cycle"],
                name="unique_account_cycle_summary",
            )
        ]

    def __str__(self) -> str:
        return f"MonthSummary({self.account.name}, {self.cycle.year}-{self.cycle.month:02d})"

    @property
    def net_worth_change(self) -> Decimal:
        return self.net_worth_end - self.net_worth_start
