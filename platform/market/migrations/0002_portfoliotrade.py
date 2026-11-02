import django.core.validators
import django.db.models.deletion
from decimal import Decimal

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("market", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PortfolioTrade",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("side", models.CharField(max_length=8, choices=[("buy", "Buy"), ("sell", "Sell")])),
                ("shares", models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)])),
                (
                    "price",
                    models.DecimalField(
                        decimal_places=4,
                        max_digits=14,
                        validators=[django.core.validators.MinValueValidator(Decimal("0.0001"))],
                    ),
                ),
                ("trade_date", models.DateField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "symbol",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="portfolio_trades",
                        to="market.symbol",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="portfolio_trades",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["trade_date", "id"],
            },
        ),
        migrations.AddIndex(
            model_name="portfoliotrade",
            index=models.Index(fields=["user", "trade_date"], name="market_trade_user_date_idx"),
        ),
    ]
