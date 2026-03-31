# Generated migration for Investment and MonthSummary models

from decimal import Decimal
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('api', '0002_alert_expense'),
    ]

    operations = [
        migrations.CreateModel(
            name='Investment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('type', models.CharField(choices=[('stocks', 'Stocks'), ('crypto', 'Cryptocurrency'), ('bonds', 'Bonds'), ('mutual_funds', 'Mutual Funds'), ('real_estate', 'Real Estate'), ('other', 'Other')], default='other', max_length=20)),
                ('total_invested', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=14)),
                ('current_value', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=14)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='investments', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Investment',
                'verbose_name_plural': 'Investments',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='MonthSummary',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('total_income', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=14)),
                ('total_expenses', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=14)),
                ('total_saved', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=14)),
                ('remaining_carried_over', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=14)),
                ('net_worth_start', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=14)),
                ('net_worth_end', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=14)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('cycle', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='summary', to='api.monthcycle')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='month_summaries', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Month Summary',
                'verbose_name_plural': 'Month Summaries',
                'ordering': ['-cycle__year', '-cycle__month'],
            },
        ),
        migrations.AddConstraint(
            model_name='monthsummary',
            constraint=models.UniqueConstraint(fields=('user', 'cycle'), name='unique_user_cycle_summary'),
        ),
    ]
