# api/tests.py

from decimal import Decimal
from django.contrib.auth.models import User
from django.test import TestCase

from api.models import FinancialProfile, MonthCycle
from api.services import run_allocation_engine, run_invest


class AllocationEngineTests(TestCase):
    def setUp(self):
        self.user    = User.objects.create_user(username="testuser", password="pass")
        self.profile = FinancialProfile.objects.create(user=self.user)

    def _make_cycle(self):
        return MonthCycle.objects.create(user=self.user, year=2026, month=3)

    # ── Normal mode ───────────────────────────────────────────────────────────

    def test_income_60k_all_buckets_filled(self):
        """With fresh profile + ₱60,000 income, all 4 buckets should be allocated."""
        cycle = self._make_cycle()
        run_allocation_engine(self.profile, cycle, Decimal("60000"))

        self.profile.refresh_from_db()
        cycle.refresh_from_db()

        # cash_on_hand receives income, then gets distributed
        self.assertEqual(self.profile.emergency_fund,  Decimal("10000.00"))
        self.assertEqual(self.profile.rigs_fund,       Decimal("10000.00"))
        self.assertEqual(self.profile.savings,         Decimal("20000.00"))
        self.assertEqual(self.profile.cash_on_hand,    Decimal("20000.00"))  # 60k-10k-10k-20k

        # Cycle budget fields
        self.assertEqual(cycle.income,                 Decimal("60000.00"))
        self.assertEqual(cycle.emergency_fund_budget,  Decimal("10000.00"))
        self.assertEqual(cycle.rigs_fund_budget,       Decimal("10000.00"))
        self.assertEqual(cycle.savings_budget,         Decimal("20000.00"))
        self.assertEqual(cycle.expenses_budget,        Decimal("7000.00"))
        self.assertEqual(cycle.wants_budget,           Decimal("3000.00"))
        self.assertEqual(cycle.remaining_budget,       Decimal("10000.00"))

        # Allocation logs: income→cash, cash→EF, cash→rigs, cash→savings
        logs = list(cycle.allocation_logs.values_list("from_bucket", "to_bucket", "amount"))
        self.assertIn(("income",      "cash_on_hand",    Decimal("60000.00")), logs)
        self.assertIn(("cash_on_hand","emergency_fund",  Decimal("10000.00")), logs)
        self.assertIn(("cash_on_hand","rigs_fund",       Decimal("10000.00")), logs)
        self.assertIn(("cash_on_hand","savings",         Decimal("20000.00")), logs)

    def test_emergency_fund_skipped_when_full(self):
        """If EF is already at ₱10,000 the engine skips Step 4."""
        self.profile.emergency_fund = Decimal("10000.00")
        self.profile.save()

        cycle = self._make_cycle()
        run_allocation_engine(self.profile, cycle, Decimal("60000"))

        cycle.refresh_from_db()
        # EF got nothing this cycle
        self.assertEqual(cycle.emergency_fund_budget, Decimal("0.00"))
        # Extra cash goes to rigs + savings instead
        self.assertEqual(cycle.rigs_fund_budget,      Decimal("10000.00"))
        self.assertEqual(cycle.savings_budget,        Decimal("20000.00"))

    # ── Survival mode ─────────────────────────────────────────────────────────

    def test_survival_mode_draws_from_emergency_fund(self):
        """Income = 0 → expenses_budget = 5,000 drawn from EF, wants = 0."""
        self.profile.emergency_fund = Decimal("15000.00")
        self.profile.save()

        cycle = self._make_cycle()
        run_allocation_engine(self.profile, cycle, Decimal("0"))

        self.profile.refresh_from_db()
        cycle.refresh_from_db()

        self.assertEqual(self.profile.emergency_fund, Decimal("10000.00"))  # 15k - 5k
        self.assertEqual(cycle.expenses_budget,        Decimal("5000.00"))
        self.assertEqual(cycle.wants_budget,           Decimal("0.00"))
        self.assertEqual(cycle.remaining_budget,       Decimal("0.00"))

        logs = list(cycle.allocation_logs.values_list("from_bucket", "to_bucket"))
        self.assertIn(("emergency_fund", "expenses_budget"), logs)

    # ── Invest ────────────────────────────────────────────────────────────────

    def test_invest_moves_savings_to_investments(self):
        """run_invest reduces savings and increases investments_total."""
        self.profile.savings = Decimal("20000.00")
        self.profile.save()

        cycle = self._make_cycle()
        run_invest(self.profile, cycle, Decimal("5000"))

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.savings,           Decimal("15000.00"))
        self.assertEqual(self.profile.investments_total, Decimal("5000.00"))

    def test_invest_raises_if_insufficient_savings(self):
        cycle = self._make_cycle()
        with self.assertRaises(ValueError):
            run_invest(self.profile, cycle, Decimal("100"))  # savings = 0
