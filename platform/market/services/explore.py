"""Price frames, hypothetical results, Plotly figures, and the chat brief for the dashboard."""

import json
import os
import re
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

BANK_CODES = {
    "ABSA", "BKG", "COOP", "DTK", "EQTY", "FMLY", "HFCK", "IMH", "KCB", "NCBA", "SBIC", "SCBK",
}


def nairobi_today():
    return datetime.now(ZoneInfo("Africa/Nairobi")).date()


def money(value):
    if value is None or pd.isna(value):
        return "—"
    return "KSh " + f"{float(value):,.2f}"


def pct(value):
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value):+.2f}%"


def price_fmt(value):
    if value is None or pd.isna(value):
        return "—"
    number = float(value)
    if abs(number) < 1:
        return f"KSh {number:.3f}"
    return f"KSh {number:,.2f}"


def parse_date(value, fallback):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return fallback


def clamp_date(value, earliest, latest):
    if value < earliest:
        return earliest
    if value > latest:
        return latest
    return value


def load_equity_frame():
    from django.core.cache import cache
    from market.models import DailyPrice

    cached = cache.get("nse-equity-frame-v1")
    if cached is not None:
        return cached
    rows = list(
        DailyPrice.objects.exclude(symbol__code__startswith="^")
        .values_list(
            "symbol__code",
            "symbol__name",
            "recorded_name",
            "trade_date",
            "day_price",
            "previous",
            "volume",
            "day_low",
            "day_high",
        )
    )
    if not rows:
        raise RuntimeError("Price data has not been imported yet.")
    data = pd.DataFrame(
        rows,
        columns=["Code", "Name", "recorded_name", "trade_date", "price", "previous", "volume", "day_low", "day_high"],
    )
    data["date"] = pd.to_datetime(data["trade_date"])
    for column in ("price", "previous", "volume", "day_low", "day_high"):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data = data.dropna(subset=["date", "price", "Code"])
    data = data.sort_values(["date", "Code"]).drop_duplicates(["date", "Code"], keep="last")
    latest_names = data.sort_values("date").groupby("Code")["recorded_name"].last()
    symbol_names = data.sort_values("date").groupby("Code")["Name"].last()
    chosen = latest_names.where(latest_names.fillna("").astype(str).str.strip() != "", symbol_names)
    data["display_name"] = data["Code"].map(chosen).fillna(data["Name"])
    cache.set("nse-equity-frame-v1", data, 60)
    return data


def company_choices(frame):
    names = frame.sort_values("date").groupby("Code")["display_name"].last()
    return [{"code": str(code), "name": str(names[code])} for code in sorted(names.index)]


def coverage(frame):
    return frame["date"].min().date(), frame["date"].max().date()


def history_for(frame, code):
    return frame[frame["Code"] == code].sort_values("date")


def nearest_on_or_before(history, day):
    before = history[history["date"] <= pd.Timestamp(day)]
    if before.empty:
        return None
    return before.iloc[-1]


def split_amount(total, codes):
    codes = list(codes)
    if not codes:
        return {}
    cents = int(round(float(total) * 100))
    base, remainder = divmod(cents, len(codes))
    return {
        code: (base + (1 if index < remainder else 0)) / 100
        for index, code in enumerate(codes)
    }


def holding_result(history, amount, purchase_date, sell_date):
    if sell_date < purchase_date:
        return None, "Choose a sell date on or after the purchase date."
    buy = nearest_on_or_before(history, purchase_date)
    sell = nearest_on_or_before(history, sell_date)
    if buy is None:
        return None, "There is no price on or before the purchase date."
    if sell is None or sell["date"] < buy["date"]:
        return None, "There is no sale price on or after that purchase."
    buy_price = float(buy["price"])
    sell_price = float(sell["price"])
    if buy_price <= 0:
        return None, "The purchase price is not usable."
    shares = int(float(amount) // buy_price)
    cash_left = float(amount) - shares * buy_price
    value = shares * sell_price
    wealth = value + cash_left
    gain = wealth - float(amount)
    gain_pct = (wealth / float(amount) - 1) * 100 if amount else 0
    return {
        "buy_date": buy["date"].date(),
        "sell_date": sell["date"].date(),
        "buy_price": buy_price,
        "sell_price": sell_price,
        "shares": shares,
        "cash_left": cash_left,
        "value": value,
        "wealth": wealth,
        "gain": gain,
        "gain_pct": gain_pct,
    }, ""


def _layout(fig, height, title):
    fig.update_layout(
        template="none",
        height=height,
        margin=dict(l=88, r=36, t=48, b=72),
        legend_title_text="",
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor="#ffffff",
            bordercolor="#0f172a",
            font=dict(family="Inter, Arial, sans-serif", size=13, color="#0f172a"),
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, Arial, sans-serif", size=13),
        title=dict(text=title or "", font=dict(size=16)),
    )
    fig.update_xaxes(showgrid=False, automargin=True, title_standoff=18)
    fig.update_yaxes(zeroline=False, automargin=True, title_standoff=16)
    fig.update_layout(margin=dict(l=88, r=36, t=48, b=72))
    return fig


def figure_json(fig):
    return json.loads(fig.to_json())


def line_figure(frame):
    fig = px.line(
        frame,
        x="date",
        y="price",
        labels={"date": "Trading date", "price": "Share price (KSh)"},
    )
    return _layout(fig, 460, "")


def candle_figure(frame, symbol):
    opened = frame["previous"].where(frame["previous"].notna(), frame["price"])
    fig = go.Figure(data=[go.Candlestick(
        x=frame["date"],
        open=opened,
        high=frame["day_high"].where(frame["day_high"].notna(), frame["price"]),
        low=frame["day_low"].where(frame["day_low"].notna(), frame["price"]),
        close=frame["price"],
        name=symbol,
        increasing_line_color="#0f766e",
        decreasing_line_color="#b42318",
    )])
    fig.update_layout(xaxis_rangeslider_visible=False)
    fig.update_yaxes(title="Price (KSh)")
    return _layout(fig, 460, "")


def indexed_window(frame, codes, start, end):
    window = frame[
        frame["Code"].isin(list(codes))
        & (frame["date"].dt.date >= start)
        & (frame["date"].dt.date <= end)
    ].copy()
    if window.empty:
        return None
    window = window.sort_values(["Code", "date"])
    window["base_price"] = window.groupby("Code")["price"].transform("first")
    window = window[window["base_price"] > 0]
    if window.empty:
        return None
    window["indexed"] = window["price"] / window["base_price"] * 100
    return window


def return_window(frame, codes, start, end, purchase):
    """Percent change from the same close the simulator would pay, not from the graph's first day.

    A KSh 2 share and a KSh 200 share then share one scale: 0% is the purchase price.
    """
    window = frame[
        frame["Code"].isin(list(codes))
        & (frame["date"].dt.date >= start)
        & (frame["date"].dt.date <= end)
    ].copy()
    if window.empty:
        return None
    window = window.sort_values(["Code", "date"])
    bases = {}
    for code in codes:
        history = history_for(frame, code)
        buy = nearest_on_or_before(history, purchase)
        if buy is not None and float(buy["price"]) > 0:
            bases[code] = float(buy["price"])
            continue
        first = window[window["Code"] == code]
        if not first.empty and float(first["price"].iloc[0]) > 0:
            bases[code] = float(first["price"].iloc[0])
    window["base_price"] = window["Code"].map(bases)
    window = window[window["base_price"].fillna(0) > 0]
    if window.empty:
        return None
    window["return_pct"] = (window["price"] / window["base_price"] - 1) * 100
    return window


def _rgba(color, alpha=0.2):
    text = str(color or "#0f766e").strip()
    if text.startswith("#") and len(text) in {4, 7}:
        hex_color = text.lstrip("#")
        if len(hex_color) == 3:
            hex_color = "".join(character * 2 for character in hex_color)
        red, green, blue = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        return f"rgba({red},{green},{blue},{alpha})"
    return text


def path_figure(window, title, bands, y="indexed", y_title=None, as_return=False):
    line_args = {}
    if as_return:
        line_args["custom_data"] = ["price"]
    fig = px.line(
        window,
        x="date",
        y=y,
        color="display_name",
        title=title,
        labels={
            "date": "Trading date",
            "display_name": "Company",
            y: y_title or ("Return since purchase (%)" if as_return else "Price path (starts at 100)"),
        },
        **line_args,
    )
    _layout(fig, 460, title)
    if as_return:
        fig.update_yaxes(
            ticksuffix="%",
            zeroline=True,
            zerolinewidth=1,
            zerolinecolor="#94a3b8",
            rangemode="tozero",
        )
        fig.update_layout(meta={"tip": "return"})
        for trace in fig.data:
            closes = []
            for row in list(trace.customdata or []):
                try:
                    closes.append(row[0])
                except (TypeError, IndexError, KeyError):
                    closes.append(row)
            trace.text = [None if value is None or pd.isna(value) else float(value) for value in closes]
            trace.meta = {"tip": "return"}
    color_by_name = {}
    for trace in fig.data:
        color_by_name[trace.name] = getattr(getattr(trace, "line", None), "color", None)
    drawn = set()
    for name, start, end, color in bands:
        key = (name, str(start), str(end))
        if key in drawn or start is None or end is None or pd.Timestamp(end) < pd.Timestamp(start):
            continue
        drawn.add(key)
        fig.add_vrect(
            x0=pd.Timestamp(start),
            x1=pd.Timestamp(end),
            fillcolor=color or _rgba(color_by_name.get(name), 0.2),
            layer="below",
            line_width=0,
        )
    return fig


def rank_figure(rows):
    frame = pd.DataFrame(rows).sort_values("gain_pct")
    fig = px.bar(
        frame,
        x="gain_pct",
        y="Code",
        orientation="h",
        hover_data=["Company", "gain"],
        labels={"gain_pct": "Return (%)", "Code": ""},
        title="Ranked by return",
    )
    fig.update_xaxes(ticksuffix="%")
    return _layout(fig, max(220, 46 * len(frame) + 80), "Ranked by return")


def stock_page(frame, symbol, start, end, style, amount, buy, sell):
    earliest, latest = coverage(frame)
    history = history_for(frame, symbol)
    if history.empty:
        return {"empty": True}
    latest_row = history.iloc[-1]
    low_row = history.loc[history["price"].idxmin()]
    high_row = history.loc[history["price"].idxmax()]
    change = change_pct = None
    if len(history) > 1:
        previous = history.iloc[-2]
        if previous["price"]:
            change = float(latest_row["price"] - previous["price"])
            change_pct = change / float(previous["price"]) * 100
    filtered = history[(history["date"].dt.date >= start) & (history["date"].dt.date <= end)]
    chart = None
    if not filtered.empty:
        chart = candle_figure(filtered, symbol) if style == "candle" else line_figure(filtered)
    result, reason = holding_result(history, amount, buy, sell)
    return {
        "empty": False,
        "company_name": str(latest_row["display_name"]),
        "latest": price_fmt(latest_row["price"]),
        "latest_date": f"{latest_row['date']:%d %b %Y}",
        "change": price_fmt(change) if change is not None else "—",
        "change_pct": pct(change_pct) if change_pct is not None else "—",
        "change_up": change is not None and change >= 0,
        "low": price_fmt(low_row["price"]),
        "low_date": f"{low_row['date']:%d %b %Y}",
        "high": price_fmt(high_row["price"]),
        "high_date": f"{high_row['date']:%d %b %Y}",
        "span_from": f"{history['date'].min():%d %b %Y}",
        "span_to": f"{history['date'].max():%d %b %Y}",
        "chart": figure_json(chart) if chart is not None else None,
        "result": None if result is None else {
            "buy_price": price_fmt(result["buy_price"]),
            "buy_date": f"{result['buy_date']:%d %b %Y}",
            "sell_price": price_fmt(result["sell_price"]),
            "sell_date": f"{result['sell_date']:%d %b %Y}",
            "shares": f"{result['shares']:,}",
            "cash_left": money(result["cash_left"]),
            "value": money(result["value"]),
            "gain": money(result["gain"]),
            "gain_pct": pct(result["gain_pct"]),
            "gain_up": result["gain"] >= 0,
        },
        "result_error": reason,
        "earliest": earliest.isoformat(),
        "latest_day": latest.isoformat(),
    }


def default_purchase(earliest, latest):
    return clamp_date(date(2024, 10, 28), earliest, latest)


def simulate_page(frame, pot, codes, alloc, buy, sell, chart_start, chart_end):
    earliest, latest = coverage(frame)
    names = frame.sort_values("date").groupby("Code")["display_name"].last().to_dict()
    holdings = []
    notes = []
    for code in codes:
        amount = float(alloc.get(code, 0))
        if amount <= 0:
            notes.append(f"{code} has no money allocated.")
            continue
        series = history_for(frame, code)
        outcome, reason = holding_result(series, amount, buy, sell)
        if outcome is None:
            notes.append(f"{code}: {reason}")
            continue
        holdings.append({
            "code": code,
            "company": names.get(code, code),
            "amount": amount,
            "amount_text": money(amount),
            **outcome,
        })
    allocated = sum(float(alloc.get(code, 0)) for code in codes)
    unallocated = float(pot) - allocated
    rows = []
    chart_rows = []
    if holdings:
        ordered = sorted(holdings, key=lambda row: (row["gain"], row["gain_pct"]), reverse=True)
        for rank, row in enumerate(ordered, start=1):
            rows.append({
                "rank": rank,
                "code": row["code"],
                "company": row["company"],
                "amount": money(row["amount"]),
                "shares": f"{row['shares']:,}",
                "bought": f"{row['buy_date']:%d %b %Y}",
                "buy_price": price_fmt(row["buy_price"]),
                "sold": f"{row['sell_date']:%d %b %Y}",
                "sell_price": price_fmt(row["sell_price"]),
                "value": money(row["value"]),
                "cash_left": money(row["cash_left"]),
                "gain": money(row["gain"]),
                "gain_up": row["gain"] >= 0,
                "gain_pct": pct(row["gain_pct"]),
            })
            chart_rows.append({
                "Code": row["code"],
                "Company": row["company"],
                "gain_pct": row["gain_pct"],
                "gain": row["gain"],
            })
        share_value = sum(row["value"] for row in holdings)
        rounding_cash = sum(row["cash_left"] for row in holdings)
        placed = sum(row["amount"] for row in holdings)
        cash_held = rounding_cash + (allocated - placed) + max(unallocated, 0)
        wealth = share_value + cash_held
        basis = float(pot) if unallocated >= -0.01 else allocated
        gain = wealth - basis
        gain_pct = (gain / basis * 100) if basis else 0
        totals = {
            "spent": money(placed - rounding_cash),
            "cash": money(cash_held),
            "wealth": money(wealth),
            "gain": money(gain),
            "gain_pct": pct(gain_pct),
            "gain_up": gain >= 0,
        }
    else:
        totals = None
    bands = []
    if sell >= buy:
        bands = [("Held", buy, sell, "rgba(15,118,110,0.22)")]
    window = return_window(frame, codes, chart_start, chart_end, buy) if codes else None
    path = path_figure(
        window,
        "",
        bands,
        y="return_pct",
        y_title="Return since purchase (%)",
        as_return=True,
    ) if window is not None else None
    return {
        "notes": notes,
        "over": allocated > float(pot) + 0.01,
        "over_text": f"The mix adds up to {money(allocated)}, which is {money(allocated - float(pot))} more than the pot." if allocated > float(pot) + 0.01 else "",
        "unallocated_text": f"Allocated {money(allocated)}. {money(unallocated)} of the pot is still unallocated cash." if unallocated > 0.01 else "",
        "rows": rows,
        "totals": totals,
        "rank": figure_json(rank_figure(chart_rows)) if chart_rows else None,
        "path": figure_json(path) if path is not None else None,
        "earliest": earliest.isoformat(),
        "latest_day": latest.isoformat(),
    }


def portfolio_page(user, frame):
    from market.services.portfolio import combine_trades, held_intervals

    earliest, latest = coverage(frame)
    saved = []
    for trade in user.portfolio_trades.select_related("symbol"):
        saved.append({
            "id": trade.id,
            "code": trade.symbol.code,
            "side": trade.side,
            "shares": trade.shares,
            "price": trade.price,
            "trade_date": trade.trade_date,
        })
    positions, error = combine_trades(saved) if saved else ({}, None)
    names = frame.sort_values("date").groupby("Code")["display_name"].last().to_dict()
    open_rows = []
    realized = Decimal("0")
    open_value = Decimal("0")
    open_cost = Decimal("0")
    missing_close = False
    for code, state in sorted(positions.items()):
        realized += state["realized"]
        if state["shares"] <= 0:
            continue
        history = history_for(frame, code)
        latest_row = nearest_on_or_before(history, nairobi_today()) if not history.empty else None
        cost = state["cost"]
        if latest_row is None:
            value = cost
            close_text = "—"
            close_date = "—"
            missing_close = True
        else:
            close_number = Decimal(str(latest_row["price"]))
            value = close_number * state["shares"]
            close_text = f"{close_number:,.2f}"
            close_date = f"{latest_row['date']:%d %b %Y}"
        profit = value - cost
        open_value += value
        open_cost += cost
        open_rows.append({
            "code": code,
            "company": names.get(code, code),
            "shares": f"{state['shares']:,}",
            "average": f"{(cost / state['shares']):,.2f}",
            "close": close_text,
            "close_date": close_date,
            "value": f"{value:,.2f}",
            "gain": f"{profit:+,.2f}",
            "gain_up": profit >= 0,
            "gain_pct": pct(float(profit / cost * 100) if cost else 0),
        })
    total_profit = open_value - open_cost + realized
    bands = [
        (names.get(code, code), opened, closed, None)
        for code, opened, closed in held_intervals(saved, latest)
    ]
    codes = sorted({trade["code"] for trade in saved})
    window = indexed_window(frame, codes, earliest, latest) if codes else None
    path = path_figure(
        window,
        "Share prices across the dates you chose",
        bands,
    ) if window is not None else None
    ledger = []
    for trade in saved:
        history = history_for(frame, trade["code"])
        exact = history[history["date"].dt.date == trade["trade_date"]]
        official = None if exact.empty else float(exact.iloc[-1]["price"])
        paid = float(trade["price"])
        ledger.append({
            "id": trade["id"],
            "date": trade["trade_date"].strftime("%d %b %Y"),
            "side": trade["side"].title(),
            "code": trade["code"],
            "shares": f"{trade['shares']:,}",
            "price": f"{paid:,.2f}",
            "official": "—" if official is None else f"{official:,.2f}",
            "gap": "—" if official is None else f"{paid - official:+,.2f}",
            "label": f"{trade['trade_date']:%d %b %Y} · {trade['side'].title()} · {trade['code']} · {trade['shares']} @ {trade['price']}",
        })
    return {
        "error": error,
        "missing_close": missing_close,
        "open_rows": open_rows,
        "shares": f"{sum(int(row['shares'].replace(',', '')) for row in open_rows):,}",
        "cost": money(open_cost),
        "value": money(open_value),
        "profit": money(total_profit),
        "profit_pct": pct(float(total_profit / open_cost * 100) if open_cost else 0),
        "profit_up": total_profit >= 0,
        "realized": money(realized) if realized else "",
        "path": figure_json(path) if path is not None else None,
        "ledger": ledger,
        "earliest": earliest.isoformat(),
        "latest_day": latest.isoformat(),
        "entry_max": max(latest, nairobi_today()).isoformat(),
        "entry_default": min(nairobi_today(), max(latest, nairobi_today())).isoformat(),
    }


def name_tokens(text):
    cleaned = str(text or "").lower()
    cleaned = re.sub(r"\s*&\s*", "", cleaned)
    return re.findall(r"[a-z0-9]+", cleaned)


def mentioned_codes(question, pairs):
    asked = set(name_tokens(question))
    hits = []
    for code, name in pairs:
        words = [token for token in name_tokens(name) if len(token) >= 4]
        if code.lower() in asked or any(token in asked for token in words):
            hits.append(code)
    return hits[:4]


def _series_text(history, with_volume):
    parts = []
    for row in history.itertuples(index=False):
        piece = f"{row.date:%Y-%m-%d} {row.price}"
        volume = getattr(row, "volume", None)
        if with_volume and pd.notna(volume):
            piece += f" vol {int(volume)}"
        parts.append(piece)
    return "; ".join(parts)


def market_context(frame, question, focus_code):
    ordered = frame.sort_values(["Code", "date"])
    pairs = [
        (str(code), str(name))
        for code, name in ordered.groupby("Code")["display_name"].last().sort_index().items()
    ]
    named = mentioned_codes(question, pairs)
    if focus_code and str(focus_code) not in named:
        named.append(str(focus_code))
    lines = [
        f"Closes run from {ordered['date'].min():%d %b %Y} to {ordered['date'].max():%d %b %Y}.",
        "Day Price is the daily close in Kenyan shillings. This list is every company in the app.",
        "For every company: latest close, record low, record high, the month-end close for the whole record, and the last 20 daily closes.",
        "Companies named in the question also include their full daily closes. Do not invent a daily close for a date that is not listed.",
    ]
    banks = []
    company_lines = []
    for code, history in ordered.groupby("Code", sort=True):
        code = str(code)
        latest = history.iloc[-1]
        name = str(latest["display_name"])
        low = history.loc[history["price"].idxmin()]
        high = history.loc[history["price"].idxmax()]
        months = history.assign(month=history["date"].dt.to_period("M")).groupby("month", sort=True).tail(1)
        extras = []
        if pd.notna(latest["volume"]):
            extras.append(f"latest volume {int(latest['volume'])}")
        if pd.notna(latest["day_low"]):
            extras.append(f"session low {latest['day_low']}")
        if pd.notna(latest["day_high"]):
            extras.append(f"session high {latest['day_high']}")
        extra_text = f"; {'; '.join(extras)}" if extras else ""
        company_lines.append(
            f"{code} {name}: latest {latest['price']} on {latest['date']:%Y-%m-%d}{extra_text}; "
            f"record low {low['price']} on {low['date']:%Y-%m-%d}; "
            f"record high {high['price']} on {high['date']:%Y-%m-%d}"
        )
        company_lines.append("month ends: " + _series_text(months, with_volume=False))
        company_lines.append("last 20 sessions: " + _series_text(history.tail(20), with_volume=True))
        if code in named:
            company_lines.append("full daily closes: " + _series_text(history, with_volume=False))
        if code in BANK_CODES or "bank" in name_tokens(name):
            banks.append(f"{code} {name}")
    if focus_code:
        lines.append(f"The page is currently showing {focus_code}.")
    lines.append("Banks: " + "; ".join(banks))
    lines.append("All companies:")
    lines.extend(company_lines)
    return "\n".join(lines)


def ask_market_bot(history, context):
    import requests

    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set.")
    model = os.environ.get("OPENROUTER_MODEL", "").strip() or "openai/gpt-6-luna-pro"
    messages = [{
        "role": "system",
        "content": (
            "You analyse Nairobi Securities Exchange daily closes for the NSE Investment Explorer. "
            "The market data lists every company. Each one has a latest close, record low, record high, month-end closes for the whole record, and the last 20 daily closes. "
            "A company named in the question also has its full daily closes. "
            "Answer a group question, such as all banks, for every company in that group from those figures. "
            "Do not say a listed company has no closing price. Do not invent a ticker or a daily close that is not in the data. "
            "Prices are Kenyan shillings. Do not give personal financial advice. Name the dates you use."
        ),
    }]
    messages.extend(history[-8:])
    if messages and messages[-1]["role"] == "user":
        messages[-1] = {
            "role": "user",
            "content": "Market data:\n" + context + "\n\nQuestion:\n" + messages[-1]["content"],
        }
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://nse.matinde.com",
            "X-Title": "NSE Investment Explorer",
        },
        json={"model": model, "temperature": 0.2, "messages": messages},
        timeout=60,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"OpenRouter returned HTTP {response.status_code}.")
    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise RuntimeError("OpenRouter returned an unreadable response.") from exc
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    text = str(content or "").strip()
    if not text:
        raise RuntimeError("OpenRouter returned an empty answer.")
    return text
