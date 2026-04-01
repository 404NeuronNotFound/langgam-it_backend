from django.contrib import admin

from .models import Alert, AllocationLog, FinancialProfile, MonthCycle, NetWorthSnapshot, Expense, Investment, MonthSummary, InvestmentAllocation


class AllocationLogInline(admin.TabularInline):
    model  = AllocationLog
    extra  = 0
    readonly_fields = ["from_bucket", "to_bucket", "amount", "timestamp"]
    can_delete = False


@admin.register(MonthCycle)
class MonthCycleAdmin(admin.ModelAdmin):
    list_display  = ["user", "year", "month", "income", "expenses_budget",
                     "wants_budget", "remaining_budget", "status", "created_at"]
    list_filter   = ["status", "year", "month"]
    search_fields = ["user__username"]
    inlines       = [AllocationLogInline]


admin.site.register(FinancialProfile)
admin.site.register(NetWorthSnapshot)
admin.site.register(AllocationLog)
admin.site.register(Alert)
admin.site.register(Expense)
admin.site.register(Investment)
admin.site.register(MonthSummary)
admin.site.register(InvestmentAllocation)


