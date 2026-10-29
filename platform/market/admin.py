from django.contrib import admin

from .models import DailyPrice, IngestRun, Symbol


@admin.register(Symbol)
class SymbolAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_index")
    search_fields = ("code", "name")
    list_filter = ("is_index",)


@admin.register(DailyPrice)
class DailyPriceAdmin(admin.ModelAdmin):
    list_display = ("symbol", "trade_date", "day_price", "volume", "source")
    list_filter = ("source", "trade_date")
    search_fields = ("symbol__code", "recorded_name")
    list_select_related = ("symbol",)
    date_hierarchy = "trade_date"


@admin.register(IngestRun)
class IngestRunAdmin(admin.ModelAdmin):
    list_display = ("kind", "status", "rows_written", "started_at", "finished_at")
    list_filter = ("kind", "status")
    readonly_fields = ("kind", "status", "started_at", "finished_at", "rows_written", "error")
