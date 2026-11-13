import re

from django import forms
from django.contrib import admin, messages
from django.db import transaction
from django.http import HttpResponseRedirect
from django.urls import reverse

from market.services.afx import SECTORS

from .models import DailyPrice, IngestRun, PendingListing, PortfolioTrade, Symbol


class PendingListingForm(forms.ModelForm):
    class Meta:
        model = PendingListing
        fields = ("name", "sector", "ticker")
        help_texts = {
            "ticker": "Assign a ticker to add this stock. The next close is stored after that.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = list(SECTORS)
        known = {key for key, _label in choices}
        current = (self.instance.sector or "").strip()
        if current and current not in known:
            choices = [(current, current), *choices]
        choices = [("", "Unknown"), *choices]
        self.fields["sector"] = forms.ChoiceField(
            choices=choices,
            required=False,
            initial=current,
            label="Sector",
        )

    def clean_ticker(self):
        code = (self.cleaned_data.get("ticker") or "").strip().upper()
        if not code:
            return ""
        if re.fullmatch(r"[A-Z0-9]{1,32}", code) is None:
            raise forms.ValidationError("Use letters and digits only.")
        isin = self.instance.isin
        clash = (
            Symbol.objects.filter(code=code)
            .exclude(isin__isnull=True)
            .exclude(isin="")
            .exclude(isin=isin)
            .first()
        )
        if clash is not None:
            raise forms.ValidationError(f"{code} already belongs to {clash.name}.")
        holder = Symbol.objects.filter(isin=isin).exclude(code=code).first()
        if holder is not None:
            raise forms.ValidationError(f"This ISIN is already {holder.code}.")
        return code


@admin.register(Symbol)
class SymbolAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "isin", "sector", "is_index")
    search_fields = ("code", "name", "isin")
    list_filter = ("is_index", "sector")


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


@admin.register(PendingListing)
class PendingListingAdmin(admin.ModelAdmin):
    form = PendingListingForm
    list_display = ("name", "isin", "sector", "day_price", "session_date")
    search_fields = ("name", "isin")
    list_filter = ("sector",)
    fields = ("name", "sector", "ticker", "isin", "session_date", "day_price", "volume", "change_pct")
    readonly_fields = ("isin", "session_date", "day_price", "volume", "change_pct")
    actions = None

    def has_add_permission(self, request):
        return False

    def response_change(self, request, obj):
        code = (obj.ticker or "").strip().upper()
        if not code:
            return super().response_change(request, obj)
        with transaction.atomic():
            symbol = Symbol.objects.filter(code=code).first()
            if symbol is None:
                Symbol.objects.create(
                    code=code,
                    name=obj.name,
                    isin=obj.isin,
                    sector=obj.sector,
                    is_index=False,
                )
            else:
                symbol.name = obj.name or symbol.name
                symbol.isin = obj.isin
                if obj.sector:
                    symbol.sector = obj.sector
                symbol.save(update_fields=["name", "isin", "sector"])
            obj.delete()
        self.message_user(request, f"{code} will be included from the next close.", messages.SUCCESS)
        return HttpResponseRedirect(reverse("admin:market_pendinglisting_changelist"))


@admin.register(IngestRun)
class IngestRunAdmin(admin.ModelAdmin):
    list_display = ("kind", "status", "rows_written", "started_at", "finished_at")
    list_filter = ("kind", "status")
    readonly_fields = ("kind", "status", "started_at", "finished_at", "rows_written", "error")
