# api/services.py
#
# Allocation engine — pure business logic, no HTTP concerns.
# Called by views; directly testable without HTTP layer.
#
# ── CORRECT ALLOCATION ORDER ──────────────────────────────────────────────────
#
#   income lands in cash_on_hand
#       ↓
#   Step 4  → emergency_fund (fill to ₱10,000 cap from cash_on_hand)
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

from .models import AllocationLog, FinancialProfile, MonthCycle, NetWorthSnapshot


# ── Constants ─────────────────────────────────────────────────────────────────

EMERGENCY_FUND_TARGET    = Decimal("10000.00")   # Step 4  cap
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
        # Draw up to ₱5,000 from emergency fund for bare-minimum expenses
        draw = min(EXPENSES_BUDGET_SURVIVAL, profile.emergency_fund)
        profile.emergency_fund -= draw
        _log(cycle, "emergency_fund", "expenses_budget", draw)

        cycle.emergency_fund_budget = Decimal("0.00")  # nothing went IN to EF
        cycle.rigs_fund_budget      = Decimal("0.00")
        cycle.savings_budget        = Decimal("0.00")
        cycle.expenses_budget       = draw              # may be < 5k if EF is low
        cycle.wants_budget          = Decimal("0.00")
        cycle.remaining_budget      = draw

        profile.save()
        NetWorthSnapshot.capture(profile)
        cycle.save()
        return cycle

    # ── NORMAL MODE ───────────────────────────────────────────────────────────

    # Step 3 — income lands in cash_on_hand
    profile.cash_on_hand += income
    _log(cycle, "income", "cash_on_hand", income)

    # Step 4 — always contribute ₱10,000 to emergency fund each cycle (safety net)
    ef_transfer = min(EMERGENCY_FUND_TARGET, profile.cash_on_hand)
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