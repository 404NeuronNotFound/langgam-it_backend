# api/signals.py
#
# Signal receivers for Langgam-It.
#
# Registered via ApiConfig.ready() in api/apps.py.
#
# Receivers:
#   1. create_financial_account  — post_save User (created only)
#      Creates FinancialAccount + 3 system Funds + initial NetWorthSnapshot
#
#   2. sync_fund_balance_on_change — post_save Fund
#      Captures NetWorthSnapshot when current_balance changes
#
#   3. sync_fund_balance_on_delete — post_delete Fund
#      Captures NetWorthSnapshot when a Fund is removed

import logging

from django.contrib.auth.models import User
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import FinancialAccount, Fund, NetWorthSnapshot

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def create_financial_account(sender, instance, created, **kwargs):
    try:
        if not created:
            return

        account = FinancialAccount.objects.create(
            user=instance,
            name=f"{instance.first_name or instance.username}'s Finances",
        )
        account.create_default_funds()
        NetWorthSnapshot.capture(account)
        logger.info(f"FinancialAccount created for {instance.username}")
    except Exception as e:
        logger.error(f"Failed to create FinancialAccount for {instance.username}: {e}")


@receiver(post_save, sender=Fund)
def sync_fund_balance_on_change(sender, instance, update_fields=None, **kwargs):
    try:
        if getattr(instance, "_skip_snapshot", False):
            return
        if update_fields and "current_balance" not in update_fields:
            return
        if not update_fields and instance.current_balance == 0:
            return

        NetWorthSnapshot.capture(instance.account)
    except Exception as e:
        logger.error(f"Failed to capture NetWorthSnapshot for Fund {instance.id}: {e}")


@receiver(post_delete, sender=Fund)
def sync_fund_balance_on_delete(sender, instance, **kwargs):
    try:
        NetWorthSnapshot.capture(instance.account)
    except Exception as e:
        logger.error(f"Failed to capture NetWorthSnapshot after Fund delete {instance.id}: {e}")
