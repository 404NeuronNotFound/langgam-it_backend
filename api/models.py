# api/models.py

from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models


# ──────────────────────────────────────────────────────────────────────
# 1. FinancialProfile  (one per user)
# ──────────────────────────────────────────────────────────────────────

class FinancialProfile(models.Model):
    """
    Stores the five fund buckets that make up a user's financial picture.

    Created lazily via get_or_create in the view layer when first accessed.
    All decimal fields default to ₱0.00.

    Buckets
    -------
    emergency_fund    — liquid safety net (receives ₱10,000 per cycle, grows continuously)
    savings           — general savings pool
    rigs_fund         — dedicated equipment fund (target: ₱10,000 per cycle)
    cash_on_hand      — physical / wallet cash + unallocated liquid money
    investments_total — total current market value of all investment assets
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="financial_profile",
    )

    emergency_fund    = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    savings           = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    rigs_fund         = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    cash_on_hand      = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    investments_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "Financial Profile"
        verbose_name_plural = "Financial Profiles"

    def __str__(self) -> str:
        return f"FinancialProfile({self.user.username})"

    @property
    def net_worth(self) -> Decimal:
        """
        Live computed sum of all five buckets.
        Not stored on this model — use NetWorthSnapshot for historical records.
        """
        return (
            self.emergency_fund
            + self.savings
            + self.rigs_fund
            + self.cash_on_hand
            + self.investments_total
        )


# ──────────────────────────────────────────────────────────────────────
# 2. NetWorthSnapshot  (immutable historical record)
# ──────────────────────────────────────────────────────────────────────

class NetWorthSnapshot(models.Model):
    """
    Immutable point-in-time record of a user's net worth.

    Created by calling NetWorthSnapshot.capture(profile) after every
    meaningful change: initial setup, income allocation, invest transfer,
    end-of-month close.

    net_worth is auto-computed in save() and is always the exact sum of
    the five bucket fields stored on this snapshot.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="net_worth_snapshots",
    )

    emergency_fund    = models.DecimalField(max_digits=14, decimal_places=2)
    savings           = models.DecimalField(max_digits=14, decimal_places=2)
    rigs_fund         = models.DecimalField(max_digits=14, decimal_places=2)
    cash_on_hand      = models.DecimalField(max_digits=14, decimal_places=2)
    investments_total = models.DecimalField(max_digits=14, decimal_places=2)

    # Auto-computed in save() — never set this manually
    net_worth = models.DecimalField(max_digits=14, decimal_places=2)

    captured_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Net Worth Snapshot"
        verbose_name_plural = "Net Worth Snapshots"
        ordering            = ["-captured_at"]

    def __str__(self) -> str:
        return (
            f"NetWorthSnapshot("
            f"{self.user.username}, "
            f"{self.captured_at:%Y-%m-%d}, "
            f"₱{self.net_worth:,.2f})"
        )

    def save(self, *args, **kwargs) -> None:
        """Auto-compute and store net_worth before every save."""
        self.net_worth = (
            self.emergency_fund
            + self.savings
            + self.rigs_fund
            + self.cash_on_hand
            + self.investments_total
        )
        super().save(*args, **kwargs)

    @classmethod
    def capture(cls, profile: FinancialProfile) -> "NetWorthSnapshot":
        """
        Factory — creates a snapshot from the current state of a FinancialProfile.

        Usage:
            snapshot = NetWorthSnapshot.capture(request.user.financial_profile)
        """
        return cls.objects.create(
            user              = profile.user,
            emergency_fund    = profile.emergency_fund,
            savings           = profile.savings,
            rigs_fund         = profile.rigs_fund,
            cash_on_hand      = profile.cash_on_hand,
            investments_total = profile.investments_total,
        )


# ──────────────────────────────────────────────────────────────────────
# 3. MonthCycle  (one record per calendar month per user)
# ──────────────────────────────────────────────────────────────────────

class MonthCycle(models.Model):
    """
    Represents a single calendar-month budget cycle for a user.

    Lifecycle
    ---------
    Created (status='active') when the user submits income via POST /api/income/.
    Closed  (status='closed') at end-of-month or when the next cycle starts.

    Allocation fields
    -----------------
    emergency_fund_budget — how much went INTO the emergency fund this cycle (₱10,000 per cycle)
    rigs_fund_budget      — how much went INTO the rigs fund this cycle
    savings_budget        — how much went INTO savings this cycle
    expenses_budget       — earmarked for needs spending (₱7,000 normal / ₱5,000 survival)
    wants_budget          — earmarked for wants spending (₱3,000 normal / ₱0 survival)
    remaining_budget      — total spendable = expenses_budget + wants_budget
    """

    STATUS_ACTIVE  = "active"
    STATUS_CLOSED  = "closed"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_CLOSED, "Closed"),
    ]

    user  = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="month_cycles",
    )
    year  = models.PositiveIntegerField()
    month = models.PositiveIntegerField()   # 1–12

    income                = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    # How much was allocated INTO each fund this cycle
    emergency_fund_budget = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    rigs_fund_budget      = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    savings_budget        = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    # Spendable budgets — earmarked portion of cash_on_hand
    expenses_budget  = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    wants_budget     = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    remaining_budget = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    status     = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Month Cycle"
        verbose_name_plural = "Month Cycles"
        ordering            = ["-year", "-month"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "year", "month"],
                name="unique_user_year_month",
            )
        ]

    def __str__(self) -> str:
        return f"MonthCycle({self.user.username}, {self.year}-{self.month:02d}, {self.status})"


# ──────────────────────────────────────────────────────────────────────
# 4. AllocationLog  (immutable ledger of every fund transfer per cycle)
# ──────────────────────────────────────────────────────────────────────

class AllocationLog(models.Model):
    """
    Immutable ledger entry recording a single fund transfer within a MonthCycle.

    from_bucket / to_bucket use string identifiers that match FinancialProfile
    field names or logical budget labels:

        'income'             — external income source
        'cash_on_hand'       — liquid cash pool
        'emergency_fund'     — safety net bucket
        'rigs_fund'          — equipment fund bucket
        'savings'            — savings bucket
        'investments_total'  — investments bucket
        'spendable_budget'   — combined expenses + wants earmark
        'expenses_budget'    — needs spending earmark
        'wants_budget'       — wants spending earmark
    """

    cycle       = models.ForeignKey(
        MonthCycle,
        on_delete=models.CASCADE,
        related_name="allocation_logs",
    )
    from_bucket = models.CharField(max_length=50)
    to_bucket   = models.CharField(max_length=50)
    amount      = models.DecimalField(max_digits=14, decimal_places=2)
    timestamp   = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Allocation Log"
        verbose_name_plural = "Allocation Logs"
        ordering            = ["timestamp"]

    def __str__(self) -> str:
        return (
            f"AllocationLog("
            f"cycle={self.cycle_id}, "
            f"{self.from_bucket} → {self.to_bucket}, "
            f"₱{self.amount:,.2f})"
        )


# ──────────────────────────────────────────────────────────────────────
# 5. Expense  (daily transaction — deducted from cash_on_hand)
# ──────────────────────────────────────────────────────────────────────

class Expense(models.Model):
    """
    Records a single spending transaction for a user within a MonthCycle.

    Every expense is deducted from cash_on_hand immediately on creation.
    The category determines which budget bucket it draws from:
        needs  → expenses_budget
        wants  → wants_budget

    After every expense is saved, the AI monitoring engine runs to check
    for overspending, daily limit breaches, hard stops, and low emergency fund.
    """

    CATEGORY_NEEDS = "needs"
    CATEGORY_WANTS = "wants"
    CATEGORY_CHOICES = [
        (CATEGORY_NEEDS, "Needs"),
        (CATEGORY_WANTS, "Wants"),
    ]

    user  = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="expenses",
    )
    cycle = models.ForeignKey(
        MonthCycle,
        on_delete=models.CASCADE,
        related_name="expenses",
    )

    amount      = models.DecimalField(max_digits=14, decimal_places=2)
    category    = models.CharField(max_length=10, choices=CATEGORY_CHOICES)
    description = models.CharField(max_length=255, blank=True, default="")
    date        = models.DateField()                    # user-supplied date of the expense

    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Expense"
        verbose_name_plural = "Expenses"
        ordering            = ["-date", "-created_at"]

    def __str__(self) -> str:
        return (
            f"Expense("
            f"{self.user.username}, "
            f"{self.category}, "
            f"₱{self.amount:,.2f}, "
            f"{self.date})"
        )


# ──────────────────────────────────────────────────────────────────────
# 6. Alert  (AI-generated spending warnings)
# ──────────────────────────────────────────────────────────────────────

class Alert(models.Model):
    """
    Stores an AI-generated warning triggered by the monitoring engine.

    Created automatically after every expense is logged. Clients poll
    GET /api/alerts/ to surface unread alerts to the user.

    Alert types
    -----------
    overspend       — actual spend is ahead of the expected daily pace
    daily_limit     — today's spending has exceeded the computed daily limit
    hard_stop       — remaining_budget has hit ₱0 (stop spending)
    emergency_low   — emergency_fund has dropped below ₱10,000

    is_read is flipped to True by PATCH /api/alerts/<id>/read/
    """

    TYPE_OVERSPEND     = "overspend"
    TYPE_DAILY_LIMIT   = "daily_limit"
    TYPE_HARD_STOP     = "hard_stop"
    TYPE_EMERGENCY_LOW = "emergency_low"

    TYPE_CHOICES = [
        (TYPE_OVERSPEND,     "Overspend"),
        (TYPE_DAILY_LIMIT,   "Daily limit exceeded"),
        (TYPE_HARD_STOP,     "Hard stop — budget depleted"),
        (TYPE_EMERGENCY_LOW, "Emergency fund low"),
    ]

    user    = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="alerts",
    )
    cycle   = models.ForeignKey(
        MonthCycle,
        on_delete=models.CASCADE,
        related_name="alerts",
    )

    type    = models.CharField(max_length=20, choices=TYPE_CHOICES)
    message = models.TextField()
    is_read = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Alert"
        verbose_name_plural = "Alerts"
        ordering            = ["-created_at"]

    def __str__(self) -> str:
        return (
            f"Alert("
            f"{self.user.username}, "
            f"{self.type}, "
            f"read={self.is_read})"
        )