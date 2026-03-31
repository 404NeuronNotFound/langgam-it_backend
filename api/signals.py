# api/signals.py
#
# Django signals that keep FinancialProfile.investments_total
# in sync with the sum of all Investment.current_value automatically.
#
# This fires on every Investment save and delete, so the profile total
# is always accurate regardless of which view or service triggers the change.

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import FinancialProfile, Investment, NetWorthSnapshot


def _sync(user) -> None:
    """Sync investments_total on the user's FinancialProfile and capture snapshot."""
    profile, _ = FinancialProfile.objects.get_or_create(user=user)
    profile.sync_investments_total()
    NetWorthSnapshot.capture(profile)


@receiver(post_save, sender=Investment)
def investment_saved(sender, instance, **kwargs) -> None:
    _sync(instance.user)


@receiver(post_delete, sender=Investment)
def investment_deleted(sender, instance, **kwargs) -> None:
    _sync(instance.user)