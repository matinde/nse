from django.db import migrations, models


def copy_sectors_and_isins(apps, schema_editor):
    Symbol = apps.get_model("market", "Symbol")
    from market.services.afx import CODE_TO_SECTOR, ISIN_TO_CODE

    code_to_isin = {}
    for isin, code in ISIN_TO_CODE.items():
        code_to_isin.setdefault(code, isin)
    for symbol in Symbol.objects.all():
        sector = CODE_TO_SECTOR.get(symbol.code, "")
        isin = code_to_isin.get(symbol.code)
        fields = []
        if sector and symbol.sector != sector:
            symbol.sector = sector
            fields.append("sector")
        if isin and not symbol.isin:
            symbol.isin = isin
            fields.append("isin")
        if fields:
            symbol.save(update_fields=fields)


class Migration(migrations.Migration):

    dependencies = [
        ("market", "0002_portfoliotrade"),
    ]

    operations = [
        migrations.AddField(
            model_name="symbol",
            name="isin",
            field=models.CharField(blank=True, max_length=16, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="symbol",
            name="sector",
            field=models.CharField(blank=True, max_length=16),
        ),
        migrations.CreateModel(
            name="PendingListing",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("isin", models.CharField(max_length=16, unique=True)),
                ("name", models.CharField(max_length=255)),
                ("sector", models.CharField(blank=True, max_length=16)),
                ("ticker", models.CharField(blank=True, max_length=32)),
                ("session_date", models.DateField()),
                ("day_price", models.DecimalField(decimal_places=4, max_digits=14)),
                ("volume", models.BigIntegerField(blank=True, null=True)),
                ("change_pct", models.DecimalField(blank=True, decimal_places=4, max_digits=12, null=True)),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.RunPython(copy_sectors_and_isins, migrations.RunPython.noop),
    ]
