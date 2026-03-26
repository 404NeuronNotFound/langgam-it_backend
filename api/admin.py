from django.contrib import admin

# Register your models here.
from .models import FinancialProfile, NetWorthSnapshot

admin.site.register(FinancialProfile)
admin.site.register(NetWorthSnapshot)