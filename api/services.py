from decimal import Decimal
from datetime import date
import calendar

from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

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


EMERGENCY_THRESHOLD = Decimal("10000.00")


def _save_fund_balance(fund: Fund) -> None:
    fund._skip_snapshot = True
    fund.save(update_fields=["current_balance"])


def _create_transfer_record(
    account: FinancialAccount,
    cycle: MonthCycle | None,
    from_fund: Fund | None,
    to_fund: Fund | None,
    amount: Decimal,
    transfer_type: str,
    note: str,
    transfer_date: date,
) -> Transfer:
    transfer_obj = Transfer(
        account=account,
        cycle=cycle,
        from_fund=from_fund,
        to_fund=to_fund,
        amount=amount,
        transfer_type=transfer_type,
        note=note,
        date=transfer_date,
    )
    transfer_obj._skip_balance_apply = True
    transfer_obj.save()
    return transfer_obj


def _months_between(start_date: date, end_date: date) -> int:
    diff = relativedelta(end_date, start_date)
    months = (diff.years * 12) + diff.months
    if diff.days > 0:
        months += 1
    return max(1, months)


# ── 1. run_setup_balances ──
def run_setup_balances(account: FinancialAccount, balances: dict) -> NetWorthSnapshot:
    # Apply initial balances to account funds and capture net worth.
    with transaction.atomic():
        for fund_id, amount in balances.items():
            amount = Decimal(amount)
            if amount <= Decimal("0.00"):
                continue
            try:
                fund = Fund.objects.get(id=fund_id, account=account)
            except Fund.DoesNotExist as exc:
                raise ValueError("Fund does not belong to this account.") from exc
            fund.current_balance = amount
            _save_fund_balance(fund)
        return NetWorthSnapshot.capture(account)


# ── 2. run_income_allocation ──
def run_income_allocation(
    account: FinancialAccount,
    cycle: MonthCycle,
    income: Decimal,
) -> MonthCycle:
    # Allocate monthly income into funds and Cash on Hand.
    with transaction.atomic():
        income = Decimal(income)
        budget_setup = MonthlyBudgetSetup.get_active(account)
        if budget_setup is None:
            raise ValueError("No active monthly budget setup found.")

        if income == Decimal("0.00"):
            scenario = MonthCycle.SCENARIO_ZERO
        elif income < budget_setup.estimated_monthly_income:
            scenario = MonthCycle.SCENARIO_LOW
        else:
            scenario = MonthCycle.SCENARIO_FULL

        cycle.income_entered = income
        cycle.income_scenario = scenario
        cycle.needs_budget_used = budget_setup.needs_budget
        cycle.wants_budget_used = budget_setup.wants_budget
        cycle.remaining_budget = budget_setup.needs_budget + budget_setup.wants_budget

        if scenario == MonthCycle.SCENARIO_ZERO:
            cycle.save(
                update_fields=[
                    "income_entered",
                    "income_scenario",
                    "needs_budget_used",
                    "wants_budget_used",
                    "remaining_budget",
                ]
            )
            return cycle

        cash_on_hand_fund = Fund.objects.get(
            account=account,
            name=Fund.SYSTEM_CASH_ON_HAND,
            type=Fund.TYPE_SYSTEM,
        )
        allocatable = income
        transfer_date = timezone.localdate()

        funds = (
            Fund.objects.filter(account=account, status=Fund.STATUS_ACTIVE)
            .exclude(id=cash_on_hand_fund.id)
            .order_by("allocation_priority", "created_at")
        )
        for fund in funds:
            if scenario == MonthCycle.SCENARIO_LOW and fund.skip_on_low_income:
                continue
            if allocatable <= Decimal("0.00"):
                break

            transfer_amount = min(fund.monthly_allocation, allocatable)
            if transfer_amount <= Decimal("0.00"):
                continue

            fund.current_balance += transfer_amount
            _save_fund_balance(fund)
            allocatable -= transfer_amount

            _create_transfer_record(
                account=account,
                cycle=cycle,
                from_fund=None,
                to_fund=fund,
                amount=transfer_amount,
                transfer_type=Transfer.TYPE_INCOME_ALLOCATION,
                note=f"Monthly allocation — {fund.name}",
                transfer_date=transfer_date,
            )

        if allocatable > Decimal("0.00"):
            cash_on_hand_fund.current_balance += allocatable
            _save_fund_balance(cash_on_hand_fund)
            _create_transfer_record(
                account=account,
                cycle=cycle,
                from_fund=None,
                to_fund=cash_on_hand_fund,
                amount=allocatable,
                transfer_type=Transfer.TYPE_MONTH_END_CARRY,
                note="Remaining income → Cash on Hand",
                transfer_date=transfer_date,
            )

        cycle.save()
        NetWorthSnapshot.capture(account)
        return cycle


# ── 3. run_survival_draw ──
def run_survival_draw(account: FinancialAccount, cycle: MonthCycle) -> Transfer:
    # Move Emergency Fund money into Cash on Hand for zero-income needs.
    with transaction.atomic():
        if cycle.income_scenario != MonthCycle.SCENARIO_ZERO:
            raise ValueError("Survival draw is only available for zero-income cycles.")

        emergency_fund = Fund.objects.get(
            account=account,
            name=Fund.SYSTEM_EMERGENCY_FUND,
            type=Fund.TYPE_SYSTEM,
        )
        cash_on_hand = Fund.objects.get(
            account=account,
            name=Fund.SYSTEM_CASH_ON_HAND,
            type=Fund.TYPE_SYSTEM,
        )

        draw_amount = min(cycle.needs_budget_used, emergency_fund.current_balance)
        if draw_amount <= Decimal("0.00"):
            raise ValueError("Emergency Fund is empty. Cannot draw for survival.")

        emergency_fund.current_balance -= draw_amount
        _save_fund_balance(emergency_fund)
        cash_on_hand.current_balance += draw_amount
        _save_fund_balance(cash_on_hand)

        transfer_obj = _create_transfer_record(
            account=account,
            cycle=cycle,
            from_fund=emergency_fund,
            to_fund=cash_on_hand,
            amount=draw_amount,
            transfer_type=Transfer.TYPE_SURVIVAL_DRAW,
            note="Emergency Fund covering needs — zero income month",
            transfer_date=timezone.localdate(),
        )
        NetWorthSnapshot.capture(account)
        return transfer_obj


# ── 4. run_transfer ──
def run_transfer(
    account: FinancialAccount,
    cycle: MonthCycle | None,
    from_fund: Fund | None,
    to_fund: Fund | None,
    amount: Decimal,
    transfer_type: str,
    note: str = "",
    transfer_date: date | None = None,
) -> Transfer:
    # Apply a user-requested transfer between funds or from an external source.
    with transaction.atomic():
        amount = Decimal(amount)
        if amount <= Decimal("0.00"):
            raise ValueError("Transfer amount must be positive.")

        if to_fund is None:
            raise ValueError("A destination fund is required.")
        if to_fund.account_id != account.id:
            raise ValueError("Destination fund does not belong to this account.")
        if from_fund is not None and from_fund.account_id != account.id:
            raise ValueError("Source fund does not belong to this account.")
        if from_fund is not None and from_fund == to_fund:
            raise ValueError("Source and destination funds cannot be the same.")

        if from_fund is not None and from_fund.current_balance < amount:
            raise ValueError(
                f"Insufficient balance in {from_fund.name}. "
                f"Available: ₱{from_fund.current_balance:,.2f}, "
                f"requested: ₱{amount:,.2f}."
            )

        note_required_types = [
            Transfer.TYPE_FUND_TO_CASH,
            Transfer.TYPE_EXTERNAL_ADD,
            Transfer.TYPE_GOAL_COMPLETED,
        ]
        if transfer_type in note_required_types and not note.strip():
            raise ValueError("A note is required for this transfer type.")

        if from_fund is not None:
            from_fund.current_balance -= amount
            _save_fund_balance(from_fund)

        to_fund.current_balance += amount
        _save_fund_balance(to_fund)

        transfer_obj = _create_transfer_record(
            account=account,
            cycle=cycle,
            from_fund=from_fund,
            to_fund=to_fund,
            amount=amount,
            transfer_type=transfer_type,
            note=note,
            transfer_date=transfer_date or timezone.localdate(),
        )
        NetWorthSnapshot.capture(account)
        return transfer_obj


# ── 5. run_expense ──
def run_expense(
    account: FinancialAccount,
    cycle: MonthCycle,
    expense: Expense,
) -> list[Alert]:
    # Deduct a persisted expense from Cash on Hand and run monitoring.
    with transaction.atomic():
        cash_on_hand = Fund.objects.get(
            account=account,
            name=Fund.SYSTEM_CASH_ON_HAND,
            type=Fund.TYPE_SYSTEM,
        )

        if expense.amount > cash_on_hand.current_balance:
            raise ValueError(
                f"Insufficient Cash on Hand. "
                f"Available: ₱{cash_on_hand.current_balance:,.2f}, "
                f"requested: ₱{expense.amount:,.2f}."
            )

        cash_on_hand.current_balance -= expense.amount
        _save_fund_balance(cash_on_hand)

        if expense.category == Expense.CATEGORY_NEEDS:
            cycle.needs_spent += expense.amount
        else:
            cycle.wants_spent += expense.amount

        cycle.remaining_budget -= expense.amount
        cycle.save(update_fields=["needs_spent", "wants_spent", "remaining_budget"])

        NetWorthSnapshot.capture(account)
        return run_monitoring_engine(account, cycle, expense)


# ── 6. run_monitoring_engine ──
def run_monitoring_engine(
    account: FinancialAccount,
    cycle: MonthCycle,
    expense: Expense,
) -> list[Alert]:
    # Create spending and goal alerts after an expense without raising exceptions.
    created_alerts = []
    try:
        today = expense.date
        total_days = calendar.monthrange(today.year, today.month)[1]
        day_of_month = today.day

        actual_spend = (
            Expense.objects.filter(cycle=cycle).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )
        original_budget = actual_spend + cycle.remaining_budget
        daily_limit = cycle.remaining_budget / Decimal(max(1, total_days - day_of_month))
        today_spent = (
            Expense.objects.filter(cycle=cycle, date=today).aggregate(total=Sum("amount"))[
                "total"
            ]
            or Decimal("0.00")
        )

        Fund.objects.get(
            account=account,
            name=Fund.SYSTEM_CASH_ON_HAND,
            type=Fund.TYPE_SYSTEM,
        )
        emergency_fund = Fund.objects.get(
            account=account,
            name=Fund.SYSTEM_EMERGENCY_FUND,
            type=Fund.TYPE_SYSTEM,
        )

        if original_budget > Decimal("0.00"):
            expected_spend = (
                Decimal(day_of_month) / Decimal(total_days)
            ) * original_budget
            if actual_spend > expected_spend:
                alert = _create_alert(
                    account,
                    cycle,
                    Alert.TYPE_OVERSPEND,
                    f"You're ahead of pace. Expected ₱{expected_spend:,.2f} by day "
                    f"{day_of_month}, actual spend ₱{actual_spend:,.2f}.",
                )
                if alert:
                    created_alerts.append(alert)

        if today_spent > daily_limit and daily_limit > Decimal("0.00"):
            alert = _create_alert(
                account,
                cycle,
                Alert.TYPE_DAILY_LIMIT,
                f"High spending day. Suggested daily limit ₱{daily_limit:,.2f}, "
                f"today's spend ₱{today_spent:,.2f}.",
            )
            if alert:
                created_alerts.append(alert)

        if cycle.remaining_budget <= Decimal("0.00"):
            alert = _create_alert(
                account,
                cycle,
                Alert.TYPE_HARD_STOP,
                "Monthly budget fully used. Further spending comes from "
                "unallocated Cash on Hand.",
            )
            if alert:
                created_alerts.append(alert)

        if emergency_fund.current_balance < EMERGENCY_THRESHOLD:
            alert = _create_alert(
                account,
                cycle,
                Alert.TYPE_EMERGENCY_LOW,
                f"Emergency Fund is ₱{emergency_fund.current_balance:,.2f}. "
                f"Target is ₱{EMERGENCY_THRESHOLD:,.2f}. "
                f"Prioritise topping it up next income entry.",
            )
            if alert:
                created_alerts.append(alert)

        goal_funds = Fund.objects.filter(
            account=account,
            type=Fund.TYPE_GOAL,
            status=Fund.STATUS_ACTIVE,
            target_amount__isnull=False,
            target_date__isnull=False,
        )
        for fund in goal_funds:
            months_left = _months_between(today, fund.target_date)
            needed_per_month = (
                fund.target_amount - fund.current_balance
            ) / Decimal(months_left)
            if (
                needed_per_month > fund.monthly_allocation
                and fund.monthly_allocation > Decimal("0.00")
            ):
                alert = _create_alert(
                    account,
                    cycle,
                    Alert.TYPE_GOAL_BEHIND,
                    f"{fund.name} is behind pace. Need ₱{needed_per_month:,.2f}/month "
                    f"but only ₱{fund.monthly_allocation:,.2f} allocated.",
                )
                if alert:
                    created_alerts.append(alert)
    except Exception:
        return created_alerts

    return created_alerts


# ── 7. run_close_month ──
def run_close_month(account: FinancialAccount, cycle: MonthCycle) -> MonthSummary:
    # Close a cycle and create or update its end-of-month summary.
    with transaction.atomic():
        net_worth_start = (
            NetWorthSnapshot.objects.filter(
                account=account,
                captured_at__gte=cycle.created_at,
            )
            .order_by("captured_at")
            .first()
        )
        net_worth_start_val = (
            net_worth_start.net_worth if net_worth_start else Decimal("0.00")
        )

        final_snapshot = NetWorthSnapshot.capture(account)
        total_allocated = (
            Transfer.objects.filter(
                account=account,
                cycle=cycle,
                transfer_type=Transfer.TYPE_INCOME_ALLOCATION,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        summary, _ = MonthSummary.objects.update_or_create(
            account=account,
            cycle=cycle,
            defaults={
                "total_income": cycle.income_entered,
                "total_needs_spent": cycle.needs_spent,
                "total_wants_spent": cycle.wants_spent,
                "total_allocated_to_funds": total_allocated,
                "net_worth_start": net_worth_start_val,
                "net_worth_end": final_snapshot.net_worth,
            },
        )

        cycle.status = MonthCycle.STATUS_CLOSED
        cycle.save(update_fields=["status"])
        return summary


def _create_alert(
    account: FinancialAccount,
    cycle: MonthCycle,
    alert_type: str,
    message: str,
) -> Alert | None:
    exists = Alert.objects.filter(
        account=account,
        cycle=cycle,
        type=alert_type,
        is_read=False,
    ).exists()
    if exists:
        return None
    return Alert.objects.create(
        account=account,
        cycle=cycle,
        type=alert_type,
        message=message,
    )
