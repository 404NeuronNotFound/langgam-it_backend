# api/models.py

from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models


# ──────────────────────────────────────────────
# 1. FinancialProfile  (one per user)
# ──────────────────────────────────────────────

class FinancialProfile(models.Model):
    """
    Stores the five fund buckets that make up a user's financial picture.
    Created automatically (via signal or explicit call) when a user registers.

    Fields
    ------
    emergency_fund   — liquid safety net
    savings          — general savings
    rigs_fund        — equipment / rig savings
    cash_on_hand     — physical / wallet cash
    investments_total — total market value of investments
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

    # ── Helpers ───────────────────────────────

    @property
    def net_worth(self) -> Decimal:
        """Live sum — not persisted here; use NetWorthSnapshot for history."""
        return (
            self.emergency_fund
            + self.savings
            + self.rigs_fund
            + self.cash_on_hand
            + self.investments_total
        )


# ──────────────────────────────────────────────
# 2. NetWorthSnapshot  (computed & stored each cycle)
# ──────────────────────────────────────────────

class NetWorthSnapshot(models.Model):
    """
    Immutable record of a user's net worth at a point in time.
    Created by calling NetWorthSnapshot.capture(profile) after every
    meaningful change to FinancialProfile.

    net_worth = emergency_fund + savings + rigs_fund + cash_on_hand + investments_total
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="net_worth_snapshots",
    )

    # Snapshot of each bucket at the moment of capture
    emergency_fund    = models.DecimalField(max_digits=14, decimal_places=2)
    savings           = models.DecimalField(max_digits=14, decimal_places=2)
    rigs_fund         = models.DecimalField(max_digits=14, decimal_places=2)
    cash_on_hand      = models.DecimalField(max_digits=14, decimal_places=2)
    investments_total = models.DecimalField(max_digits=14, decimal_places=2)

    # Computed total — auto-filled on save
    net_worth = models.DecimalField(max_digits=14, decimal_places=2)

    captured_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Net Worth Snapshot"
        verbose_name_plural = "Net Worth Snapshots"
        ordering            = ["-captured_at"]

    def __str__(self) -> str:
        return f"NetWorthSnapshot({self.user.username}, {self.captured_at:%Y-%m-%d}, ₱{self.net_worth:,.2f})"

    def save(self, *args, **kwargs) -> None:
        """Auto-compute net_worth before persisting."""
        self.net_worth = (
            self.emergency_fund
            + self.savings
            + self.rigs_fund
            + self.cash_on_hand
            + self.investments_total
        )
        super().save(*args, **kwargs)

    # ── Factory ───────────────────────────────

    @classmethod
    def capture(cls, profile: "FinancialProfile") -> "NetWorthSnapshot":
        """
        Convenience factory: snapshot the current state of a FinancialProfile.

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