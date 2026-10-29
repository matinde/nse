# Generated for the market app.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Symbol",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=32, unique=True)),
                ("name", models.CharField(max_length=255)),
                ("is_index", models.BooleanField(default=False)),
            ],
            options={
                "ordering": ["code"],
            },
        ),
        migrations.CreateModel(
            name="IngestRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(max_length=16)),
                ("status", models.CharField(default="running", max_length=16)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("rows_written", models.PositiveIntegerField(default=0)),
                ("error", models.TextField(blank=True)),
            ],
            options={
                "ordering": ["-started_at"],
            },
        ),
        migrations.CreateModel(
            name="DailyPrice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("trade_date", models.DateField()),
                ("recorded_name", models.CharField(blank=True, max_length=255)),
                ("day_price", models.DecimalField(decimal_places=4, max_digits=14)),
                ("previous", models.DecimalField(blank=True, decimal_places=4, max_digits=14, null=True)),
                ("change", models.DecimalField(blank=True, decimal_places=4, max_digits=14, null=True)),
                ("change_pct", models.DecimalField(blank=True, decimal_places=4, max_digits=12, null=True)),
                ("volume", models.BigIntegerField(blank=True, null=True)),
                ("day_low", models.DecimalField(blank=True, decimal_places=4, max_digits=14, null=True)),
                ("day_high", models.DecimalField(blank=True, decimal_places=4, max_digits=14, null=True)),
                ("source", models.CharField(max_length=16)),
                ("fetched_at", models.DateTimeField(auto_now=True)),
                (
                    "symbol",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="prices", to="market.symbol"),
                ),
            ],
            options={
                "ordering": ["-trade_date", "symbol"],
                "indexes": [models.Index(fields=["trade_date"], name="market_dp_trade_date_idx")],
                "constraints": [
                    models.UniqueConstraint(fields=("symbol", "trade_date"), name="uniq_symbol_trade_date")
                ],
            },
        ),
    ]
