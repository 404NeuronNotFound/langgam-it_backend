# Generated migration for InvestmentAllocation model

from decimal import Decimal
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('api', '0003_investment_monthsummary'),
    ]

    operations = [
        migrations.CreateModel(
            name='InvestmentAllocation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('total_allocated', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=14)),
                ('total_current_value', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=14)),
                ('total_profit_loss', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=14)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='investment_allocation', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Investment Allocation',
                'verbose_name_plural': 'Investment Allocations',
            },
        ),
    ]
