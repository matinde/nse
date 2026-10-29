from django.db import models


class Symbol(models.Model):
    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=255)
    is_index = models.BooleanField(default=False)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.code


class DailyPrice(models.Model):
    SOURCE_CSV = "csv"
    SOURCE_BOARD = "board"
    SOURCE_CHOICES = [
        (SOURCE_CSV, "CSV"),
        (SOURCE_BOARD, "Board"),
    ]

    symbol = models.ForeignKey(Symbol, on_delete=models.CASCADE, related_name="prices")
    trade_date = models.DateField()
    recorded_name = models.CharField(max_length=255, blank=True)
    day_price = models.DecimalField(max_digits=14, decimal_places=4)
    previous = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    change = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    change_pct = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    volume = models.BigIntegerField(null=True, blank=True)
    day_low = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    day_high = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES)
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["symbol", "trade_date"],
                name="uniq_symbol_trade_date",
            )
        ]
        indexes = [models.Index(fields=["trade_date"])]
        ordering = ["-trade_date", "symbol"]

    def __str__(self):
        return f"{self.symbol.code} {self.trade_date}"


class IngestRun(models.Model):
    KIND_CSV = "csv"
    KIND_BOARD = "board"
    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"

    kind = models.CharField(max_length=16)
    status = models.CharField(max_length=16, default=STATUS_RUNNING)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    rows_written = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.kind} {self.status} {self.started_at:%Y-%m-%d %H:%M}"
