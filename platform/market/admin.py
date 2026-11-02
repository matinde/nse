from django.contrib import admin

from .models import DailyPrice, IngestRun, PortfolioTrade, Symbol


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


@admin.register(PortfolioTrade)
class PortfolioTradeAdmin(admin.ModelAdmin):
    list_display = ("user", "symbol", "side", "shares", "price", "trade_date", "created_at")
    list_filter = ("side", "trade_date")
    search_fields = ("user__username", "symbol__code", "symbol__name")
    autocomplete_fields = ("user", "symbol")
    list_select_related = ("user", "symbol")
    date_hierarchy = "trade_date"


@admin.register(IngestRun)
class IngestRunAdmin(admin.ModelAdmin):
    list_display = ("kind", "status", "rows_written", "started_at", "finished_at")
    list_filter = ("kind", "status")
    readonly_fields = ("kind", "status", "started_at", "finished_at", "rows_written", "error")
