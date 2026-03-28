# api/services.py
#
# Allocation engine — pure business logic, no HTTP concerns.
# Called by views; directly testable without HTTP layer.
#
# ── CORRECT ALLOCATION ORDER ──────────────────────────────────────────────────
#
#   income lands in cash_on_hand
#       ↓
#   Step 4  → emergency_fund (₱10,000 per cycle, grows continuously)
#       ↓
#   Step 5  → reserve expenses_budget (₱7,000) + wants_budget (₱3,000)
#             these stay in cash_on_hand but are earmarked as "spendable"
#             remaining_budget = ₱10,000
#       ↓
#   Step 6  → rigs_fund (up to ₱10,000 cap from cash_on_hand)
#       ↓
#   Step 7  → savings (up to ₱20,000 cap from cash_on_hand)
#       ↓
#   leftover stays in cash_on_hand for bills, extras, etc.
#
# ── SURVIVAL MODE (income == 0) ───────────────────────────────────────────────
#
#   expenses_budget = ₱5,000  (drawn from emergency_fund)
#   wants_budget    = ₱0
#   remaining_budget = ₱0
#
# ─────────────────────────────────────────────────────────────────────────────

from decimal import Decimal
import calendar
from datetime import date

from .models import Alert, AllocationLog, Expense, FinancialProfile, MonthCycle, NetWorthSnapshot


# ── Constants ─────────────────────────────────────────────────────────────────

EMERGENCY_FUND_ALLOCATION = Decimal("10000.00")  # Step 4  per cycle allocation
RIGS_FUND_CAP            = Decimal("10000.00")   # Step 6  cap per cycle
SAVINGS_CAP              = Decimal("20000.00")   # Step 7  cap per cycle

EXPENSES_BUDGET_NORMAL   = Decimal("7000.00")    # Step 5  fixed needs allowance
WANTS_BUDGET_NORMAL      = Decimal("3000.00")    # Step 5  fixed wants allowance
EXPENSES_BUDGET_SURVIVAL = Decimal("5000.00")    # Step 10 reduced in survival mode


# ── Helper ────────────────────────────────────────────────────────────────────

def _log(cycle: MonthCycle, from_bucket: str, to_bucket: str, amount: Decimal) -> None:
    """Write an AllocationLog entry. Silently skips zero-amount transfers."""
    if amount > Decimal("0.00"):
        AllocationLog.objects.create(
            cycle=cycle,
            from_bucket=from_bucket,
            to_bucket=to_bucket,
            amount=amount,
        )


# ── Main allocation engine ────────────────────────────────────────────────────

def run_allocation_engine(
    profile: FinancialProfile,
    cycle: MonthCycle,
    income: Decimal,
) -> MonthCycle:
    """
    Execute the full monthly allocation pipeline.

    Mutates `profile` and `cycle` in place, saves both, captures a
    NetWorthSnapshot, and returns the updated cycle.

    All bucket movements are deducted from cash_on_hand in sequence so the
    remaining cash_on_hand after allocation represents genuinely unallocated
    liquid money (bills, day-to-day extras).
    """

    cycle.income = income

    # ── SURVIVAL MODE ─────────────────────────────────────────────────────────
    if income == Decimal("0.00"):
        # Draw up to ₱5,000 from emergency_fund and put it in cash_on_hand
        # so the user has real spendable money to cover their month.
        draw = min(EXPENSES_BUDGET_SURVIVAL, profile.emergency_fund)
        profile.emergency_fund -= draw
        profile.cash_on_hand   += draw                          # ← money is now spendable
        _log(cycle, "emergency_fund", "cash_on_hand", draw)

        cycle.emergency_fund_budget = Decimal("0.00")           # nothing went IN to EF
        cycle.rigs_fund_budget      = Decimal("0.00")
        cycle.savings_budget        = Decimal("0.00")
        cycle.expenses_budget       = draw                      # earmarked for needs
        cycle.wants_budget          = Decimal("0.00")
        cycle.remaining_budget      = draw                      # total they can spend

        profile.save()
        NetWorthSnapshot.capture(profile)
        cycle.save()
        return cycle

    # ── NORMAL MODE ───────────────────────────────────────────────────────────

    # Step 3 — income lands in cash_on_hand
    profile.cash_on_hand += income
    _log(cycle, "income", "cash_on_hand", income)

    # Step 4 — allocate ₱10,000 to emergency fund every cycle (priority #1)
    # Emergency fund grows continuously as a safety net, no cap
    ef_transfer = min(EMERGENCY_FUND_ALLOCATION, profile.cash_on_hand)
    if ef_transfer > Decimal("0.00"):
        profile.emergency_fund += ef_transfer
        profile.cash_on_hand   -= ef_transfer
        _log(cycle, "cash_on_hand", "emergency_fund", ef_transfer)
    cycle.emergency_fund_budget = ef_transfer

    # Step 5 — reserve spendable budget from cash_on_hand
    # The ₱10,000 (₱7k needs + ₱3k wants) stays in cash_on_hand as earmarked
    # spending money. We deduct it now so later steps (rigs, savings) only
    # allocate from what remains AFTER the user's living expenses are covered.
    spendable = EXPENSES_BUDGET_NORMAL + WANTS_BUDGET_NORMAL   # ₱10,000
    spendable_reserved = min(spendable, profile.cash_on_hand)
    profile.cash_on_hand -= spendable_reserved
    _log(cycle, "cash_on_hand", "spendable_budget", spendable_reserved)

    # Split the reserved amount proportionally if not enough for both
    if spendable_reserved >= spendable:
        cycle.expenses_budget = EXPENSES_BUDGET_NORMAL
        cycle.wants_budget    = WANTS_BUDGET_NORMAL
    else:
        # Prioritise needs over wants if cash is tight
        cycle.expenses_budget = min(EXPENSES_BUDGET_NORMAL, spendable_reserved)
        cycle.wants_budget    = max(
            Decimal("0.00"),
            spendable_reserved - cycle.expenses_budget,
        )

    cycle.remaining_budget = cycle.expenses_budget + cycle.wants_budget

    # Step 6 — rigs fund (up to ₱10,000 or whatever cash remains)
    rigs_transfer = min(RIGS_FUND_CAP, profile.cash_on_hand)
    if rigs_transfer > Decimal("0.00"):
        profile.rigs_fund    += rigs_transfer
        profile.cash_on_hand -= rigs_transfer
        _log(cycle, "cash_on_hand", "rigs_fund", rigs_transfer)
    cycle.rigs_fund_budget = rigs_transfer

    # Step 7 — savings (up to ₱20,000 or whatever cash remains)
    savings_transfer = min(SAVINGS_CAP, profile.cash_on_hand)
    if savings_transfer > Decimal("0.00"):
        profile.savings      += savings_transfer
        profile.cash_on_hand -= savings_transfer
        _log(cycle, "cash_on_hand", "savings", savings_transfer)
    cycle.savings_budget = savings_transfer

    # Whatever remains in cash_on_hand is genuinely unallocated liquid cash
    # (covers the earmarked spendable + any leftover after all allocations)
    # Add the reserved spendable back so cash_on_hand reflects the full
    # amount the user can actually spend day-to-day.
    profile.cash_on_hand += spendable_reserved

    profile.save()
    NetWorthSnapshot.capture(profile)
    cycle.save()
    return cycle


# ── Invest engine ─────────────────────────────────────────────────────────────

def run_invest(
    profile: FinancialProfile,
    cycle: MonthCycle,
    amount: Decimal,
) -> FinancialProfile:
    """
    Step 8 — Move `amount` from savings → investments_total.

    Raises ValueError if the amount is non-positive or exceeds available savings.
    Logs the transfer and captures a NetWorthSnapshot.
    """
    if amount <= Decimal("0.00"):
        raise ValueError("Investment amount must be positive.")

    if amount > profile.savings:
        raise ValueError(
            f"Insufficient savings. "
            f"Available: ₱{profile.savings:,.2f}, requested: ₱{amount:,.2f}."
        )

    profile.savings           -= amount
    profile.investments_total += amount
    profile.save()

    _log(cycle, "savings", "investments_total", amount)
    NetWorthSnapshot.capture(profile)

    return profile


# ── Expense engine ────────────────────────────────────────────────────────────

def run_expense(
    profile: FinancialProfile,
    cycle: MonthCycle,
    expense: Expense,
) -> list["Alert"]:
    """
    Steps 14 & 15 — Deduct an expense from the correct budget bucket
    and from cash_on_hand, then run the AI monitoring engine.

    Deduction rules
    ---------------
    needs  → expenses_budget -= amount
    wants  → wants_budget    -= amount
    both   → remaining_budget -= amount
             cash_on_hand     -= amount  (actual money leaves the wallet)

    Budget buckets are allowed to go negative — this reflects overspending
    reality and lets the monitoring engine catch it rather than hard-blocking.

    Returns a list of Alert objects created by the monitoring engine.
    """
    amount = expense.amount

    # Step 14 — deduct from the correct category bucket
    if expense.category == Expense.CATEGORY_NEEDS:
        cycle.expenses_budget -= amount
    else:
        cycle.wants_budget -= amount

    # Step 15 — deduct from totals
    cycle.remaining_budget -= amount
    cycle.save()

    profile.cash_on_hand -= amount
    profile.save()

    # Capture net worth snapshot after expense deduction
    NetWorthSnapshot.capture(profile)

    # Step 16–19 — run AI monitoring engine and return any alerts created
    return run_monitoring_engine(profile, cycle, expense)


# ── AI Monitoring engine ──────────────────────────────────────────────────────

EMERGENCY_FUND_THRESHOLD = Decimal("10000.00")


def _create_alert(
    user,
    cycle: MonthCycle,
    alert_type: str,
    message: str,
) -> "Alert":
    """
    Create a single Alert. Deduplicates within the same cycle — if an identical
    unread alert already exists for this type + cycle, skip creating a new one.
    """
    exists = Alert.objects.filter(
        user=user,
        cycle=cycle,
        type=alert_type,
        is_read=False,
    ).exists()

    if not exists:
        return Alert.objects.create(
            user=user,
            cycle=cycle,
            type=alert_type,
            message=message,
        )
    return None


def run_monitoring_engine(
    profile: FinancialProfile,
    cycle: MonthCycle,
    expense: Expense,
) -> list["Alert"]:
    """
    Runs after every expense. Evaluates Steps 16–19 in order and creates
    Alert records for any thresholds that are breached.

    Returns a list of the Alert objects that were created (may be empty).

    Step 16 — Overspending check
        expected_spend = (today_day / total_days_in_month) * total_budget
        IF actual_spend > expected_spend → ALERT overspend

    Step 17 — Daily limit check
        daily_limit = remaining_budget / remaining_days
        IF today_spent > daily_limit → ALERT daily_limit

    Step 18 — Hard stop
        IF remaining_budget <= 0 → ALERT hard_stop

    Step 19 — Emergency fund warning
        IF emergency_fund < 10,000 → ALERT emergency_low
    """
    today          = expense.date
    total_days     = calendar.monthrange(today.year, today.month)[1]
    day_of_month   = today.day
    remaining_days = max(1, total_days - day_of_month)   # never divide by zero

    # Total budget for this cycle (expenses + wants combined)
    total_budget = cycle.expenses_budget + cycle.wants_budget + (
        # add back what's already been spent to get the original budget
        Decimal("0.00")   # remaining_budget already reflects deductions
    )

    # Actual spend = original_budget - remaining_budget
    # Original budget = remaining_budget + amount already spent
    # We derive it from cycle fields rather than summing all expenses
    original_budget = (
        cycle.expenses_budget
        + cycle.wants_budget
        + cycle.remaining_budget.to_integral_value()    # avoid rounding drift
    )
    # Simpler: query total expenses for this cycle
    actual_spend = (
        Expense.objects
        .filter(cycle=cycle)
        .values_list("amount", flat=True)
    )
    actual_spend = sum(actual_spend, Decimal("0.00"))

    # Derive original budget = actual_spend + remaining_budget
    # (remaining_budget is already post-deduction from this expense)
    original_budget = actual_spend + cycle.remaining_budget

    created_alerts: list[Alert] = []

    # ── Step 16: Overspending check ───────────────────────────────────────────
    if original_budget > Decimal("0.00"):
        expected_spend = (Decimal(day_of_month) / Decimal(total_days)) * original_budget
        if actual_spend > expected_spend:
            alert = _create_alert(
                user       = expense.user,
                cycle      = cycle,
                alert_type = Alert.TYPE_OVERSPEND,
                message    = (
                    f"You're overspending. "
                    f"Expected spend by day {day_of_month}: ₱{expected_spend:,.2f}. "
                    f"Actual spend: ₱{actual_spend:,.2f}."
                ),
            )
            if alert:
                created_alerts.append(alert)

    # ── Step 17: Daily limit check ────────────────────────────────────────────
    daily_limit = cycle.remaining_budget / Decimal(remaining_days)

    today_spent = (
        Expense.objects
        .filter(cycle=cycle, date=today)
        .values_list("amount", flat=True)
    )
    today_spent = sum(today_spent, Decimal("0.00"))

    if today_spent > daily_limit:
        alert = _create_alert(
            user       = expense.user,
            cycle      = cycle,
            alert_type = Alert.TYPE_DAILY_LIMIT,
            message    = (
                f"Daily limit exceeded. "
                f"Today's limit: ₱{daily_limit:,.2f}. "
                f"Today's spend: ₱{today_spent:,.2f}."
            ),
        )
        if alert:
            created_alerts.append(alert)

    # ── Step 18: Hard stop ────────────────────────────────────────────────────
    if cycle.remaining_budget <= Decimal("0.00"):
        alert = _create_alert(
            user       = expense.user,
            cycle      = cycle,
            alert_type = Alert.TYPE_HARD_STOP,
            message    = (
                "STOP SPENDING. Your monthly budget has been fully used up. "
                "Any further spending comes out of your unallocated cash."
            ),
        )
        if alert:
            created_alerts.append(alert)

    # ── Step 19: Emergency fund warning ──────────────────────────────────────
    if profile.emergency_fund < EMERGENCY_FUND_THRESHOLD:
        alert = _create_alert(
            user       = expense.user,
            cycle      = cycle,
            alert_type = Alert.TYPE_EMERGENCY_LOW,
            message    = (
                f"Emergency fund is low: ₱{profile.emergency_fund:,.2f}. "
                f"Target is ₱{EMERGENCY_FUND_THRESHOLD:,.2f}. "
                f"Prioritise topping it up next month."
            ),
        )
        if alert:
            created_alerts.append(alert)

    return created_alerts