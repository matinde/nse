import os
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import create_engine

st.set_page_config(
    page_title="NSE Investment Explorer",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
:root { --ink:#17243b; --muted:#6d7b91; --teal:#087f8c; }
.block-container { padding-top: 1.35rem; padding-bottom: 3rem; max-width: 1500px; }
[data-testid="stAppViewContainer"] { background: #f5f7fb; }
[data-testid="stSidebar"] { background: #101b2d; }
[data-testid="stSidebar"] * { color: #eef4ff !important; }
.hero {
  padding: 1.45rem 1.6rem; border-radius: 20px;
  background: linear-gradient(120deg,#101b2d 0%,#183d59 65%,#087f8c 100%);
  color: white; margin-bottom: 1.2rem;
}
.hero h1 { color:white; margin:0; font-size:2rem; letter-spacing:-.03em; }
.hero p { color:#d8e8f2; margin:.45rem 0 0 0; font-size:1rem; }
.section-title { font-size:1.25rem; font-weight:750; color:#17243b; margin:.6rem 0 .2rem; }
.subtle { color:#6d7b91; font-size:.88rem; }
div[data-testid="stMetric"] {
  background:white; border:1px solid #e5eaf2; padding:16px 18px;
  border-radius:16px; box-shadow:0 3px 12px rgba(16,27,45,.035);
}
div[data-testid="stMetricLabel"] { color:#63728a; }
div[data-testid="stMetricValue"] { color:#17243b; }
div[data-testid="stMetricDelta"] { font-weight:650; }
.fit-stat {
  background: white; border: 1px solid #e5eaf2; border-radius: 16px;
  padding: 12px 14px; min-height: 88px;
  box-shadow: 0 3px 12px rgba(16,27,45,.035);
}
.fit-label { color: #63728a; font-size: .82rem; font-weight: 650; }
.fit-value {
  color: #17243b; font-size: 1.05rem; font-weight: 750;
  line-height: 1.3; overflow-wrap: anywhere; margin-top: .28rem;
}
.fit-delta { font-size: .85rem; font-weight: 650; margin-top: .15rem; }
div[data-testid="stTabs"] button { font-weight:650; }
div[data-testid="stAlert"] { border-radius:12px; }
.invest-anchor { display:none; }
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .invest-anchor) {
  background: #d5ddd6;
  border: 1px solid #b7c3b8;
  border-radius: 18px;
  padding: 0.85rem 1.15rem 1.2rem;
  margin: 0.85rem 0 1rem;
}
</style>
""", unsafe_allow_html=True)

def database_url():
    from urllib.parse import quote_plus

    password = os.environ.get("POSTGRES_PASSWORD", "").strip()
    if password:
        user = quote_plus(os.environ.get("POSTGRES_USER", "nse").strip() or "nse")
        name = quote_plus(os.environ.get("POSTGRES_DB", "nse").strip() or "nse")
        host = os.environ.get("POSTGRES_HOST", "db").strip() or "db"
        port = os.environ.get("POSTGRES_PORT", "5432").strip() or "5432"
        return f"postgresql+psycopg://{user}:{quote_plus(password)}@{host}:{port}/{name}"
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "POSTGRES_PASSWORD is not set. Start the stack with docker compose so the explorer can read Postgres."
        )
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and "+psycopg" not in url.split("://", 1)[0]:
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


@st.cache_data(show_spinner="Loading NSE price history…", ttl=60)
def load_data():
    engine = create_engine(database_url())
    data = pd.read_sql(
        """
        SELECT s.code AS code,
               COALESCE(NULLIF(p.recorded_name, ''), s.name) AS name,
               p.trade_date AS trade_date,
               p.day_price AS price,
               p.volume AS volume,
               p.day_low AS day_low,
               p.day_high AS day_high,
               p.previous AS previous,
               p.change AS change,
               p.change_pct AS change_pct
        FROM market_dailyprice p
        JOIN market_symbol s ON s.id = p.symbol_id
        """,
        engine,
    )
    if data.empty:
        raise RuntimeError(
            "Price data has not been imported yet. The web service runs import_csvs when the stack starts."
        )
    data = data.rename(columns={"code": "Code", "name": "Name", "trade_date": "date"})
    data["date"] = pd.to_datetime(data["date"])
    for column in ("price", "volume", "day_low", "day_high", "previous", "change", "change_pct"):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data = data.dropna(subset=["date", "price", "Code"])
    data = data.sort_values(["date", "Code", "Name"]).drop_duplicates(["date", "Code"], keep="last")
    latest_names = data.sort_values("date").groupby("Code")["Name"].last().to_dict()
    data["display_name"] = data["Code"].map(latest_names).fillna(data["Name"])
    data["year"] = data["date"].dt.year
    return data, []

def money(v):
    if pd.isna(v):
        return "—"
    return "KSh " + f"{v:,.2f}"

def pct(v):
    if pd.isna(v):
        return "—"
    return f"{v:+.2f}%"

def price_fmt(v):
    if pd.isna(v):
        return "—"
    if abs(v) < 1:
        return f"KSh {v:.3f}"
    return f"KSh {v:,.2f}"

def fit_stat(label, value, delta=None):
    delta_html = ""
    if delta:
        color = "#0f7b4c" if str(delta).strip().startswith("+") else "#b42318"
        delta_html = f"<div class='fit-delta' style='color:{color}'>{delta}</div>"
    st.markdown(
        f"<div class='fit-stat'><div class='fit-label'>{label}</div>"
        f"<div class='fit-value'>{value}</div>{delta_html}</div>",
        unsafe_allow_html=True,
    )

def nearest_on_or_before(history, date):
    before = history[history["date"] <= pd.Timestamp(date)]
    if before.empty:
        return None
    return before.iloc[-1]

def split_amount(total, codes):
    """Divide a cash total across codes so the parts add back to the total."""
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
    """Whole shares bought at the close on or before purchase, valued at the close on or before sale."""
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
    shares = int(amount // buy_price)
    cash_left = amount - shares * buy_price
    value = shares * sell_price
    wealth = value + cash_left
    gain = wealth - amount
    gain_pct = (wealth / amount - 1) * 100 if amount else 0
    return {
        "buy_date": buy["date"],
        "sell_date": sell["date"],
        "buy_price": buy_price,
        "sell_price": sell_price,
        "shares": shares,
        "cash_left": cash_left,
        "value": value,
        "wealth": wealth,
        "gain": gain,
        "gain_pct": gain_pct,
    }, ""

def setup_django():
    import django
    from django.apps import apps

    if apps.ready:
        return
    root = Path(__file__).resolve().parent
    for path in (root, root / "platform"):
        if (path / "config" / "settings.py").exists():
            sys.path.insert(0, str(path))
            break
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()

def nairobi_today():
    return datetime.now(ZoneInfo("Africa/Nairobi")).date()

def signed_in_user():
    from django.contrib.auth import get_user_model
    from django.db import close_old_connections

    close_old_connections()
    user_id = st.session_state.get("user_id")
    if not user_id:
        return None
    user = get_user_model().objects.filter(pk=user_id, is_active=True).first()
    if user is None:
        st.session_state.pop("user_id", None)
    return user

def show_login():
    st.markdown("""
<div class="hero">
  <h1>📈 NSE Investment Explorer</h1>
  <p>Log in to see Nairobi Securities Exchange prices and your portfolio.</p>
</div>
""", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Log in</div>", unsafe_allow_html=True)
    st.caption("An administrator creates your account. There is no registration on this site.")
    with st.form("login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")
    if submitted:
        from django.contrib.auth import authenticate

        user = authenticate(username=username.strip(), password=password)
        if user is None or not user.is_active:
            st.error("That username or password is not valid.")
        else:
            st.session_state["user_id"] = user.pk
            st.rerun()
    st.stop()

def trade_rows(user):
    from market.models import PortfolioTrade

    rows = []
    for trade in PortfolioTrade.objects.filter(user=user).select_related("symbol"):
        rows.append({
            "id": trade.id,
            "code": trade.symbol.code,
            "side": trade.side,
            "shares": trade.shares,
            "price": trade.price,
            "trade_date": trade.trade_date,
        })
    return rows

def official_close(equity_data, code, day):
    history = equity_data[equity_data["Code"] == code]
    exact = history[history["date"].dt.date == day]
    if exact.empty:
        return None
    return float(exact.iloc[-1]["price"])

def render_portfolio(user, equity_data, symbols, min_date, max_date):
    from market.models import PortfolioTrade, Symbol
    from market.services.portfolio import combine_trades, held_intervals

    st.markdown("<div class='section-title'>My portfolio</div>", unsafe_allow_html=True)
    st.caption("These trades are saved to your account. Holdings are valued at the latest official close. A price you type can differ from that close.")
    entry_max = max(max_date, nairobi_today())
    entry_default = min(nairobi_today(), entry_max)
    with st.form("add_trade"):
        form_left, form_mid, form_right = st.columns(3)
        with form_left:
            trade_code = st.selectbox("Stock", symbols, index=symbols.index("DTK") if "DTK" in symbols else 0)
            trade_side = st.selectbox("Side", ["Buy", "Sell"])
        with form_mid:
            trade_shares = st.number_input("Shares", min_value=1, step=1, value=1)
            trade_price = st.number_input("Price per share (KSh)", min_value=0.01, value=1.00, step=0.01, format="%.2f")
        with form_right:
            trade_date = st.date_input("Trade date", value=entry_default, min_value=min_date, max_value=entry_max)
        save_trade = st.form_submit_button("Save trade")
    if save_trade:
        draft = trade_rows(user)
        draft.append({
            "id": None,
            "code": trade_code,
            "side": trade_side.lower(),
            "shares": int(trade_shares),
            "price": Decimal(str(trade_price)),
            "trade_date": trade_date,
        })
        _positions, error = combine_trades(draft)
        if error:
            st.error(error)
        else:
            symbol = Symbol.objects.filter(code=trade_code).first()
            if symbol is None:
                st.error(f"{trade_code} is not in the price database yet.")
            else:
                PortfolioTrade.objects.create(
                    user=user,
                    symbol=symbol,
                    side=trade_side.lower(),
                    shares=int(trade_shares),
                    price=Decimal(str(trade_price)),
                    trade_date=trade_date,
                )
                st.rerun()

    saved = trade_rows(user)
    if not saved:
        st.info("No trades yet. Add a buy to start this portfolio.")
        return
    positions, error = combine_trades(saved)
    if error:
        st.error(error)

    names = equity_data.sort_values("date").groupby("Code")["display_name"].last().to_dict()
    open_rows = []
    realized = Decimal("0")
    open_value = Decimal("0")
    open_cost = Decimal("0")
    for code, state in sorted(positions.items()):
        realized += state["realized"]
        if state["shares"] <= 0:
            continue
        history = equity_data[equity_data["Code"] == code].sort_values("date")
        latest = nearest_on_or_before(history, nairobi_today()) if not history.empty else None
        cost = state["cost"]
        if latest is None:
            value = cost
            close_text = "—"
            close_date = "—"
            close_number = None
        else:
            close_number = Decimal(str(latest["price"]))
            value = close_number * state["shares"]
            close_text = f"{close_number:,.2f}"
            close_date = f"{latest['date']:%d %b %Y}"
        profit = value - cost
        average = cost / state["shares"]
        open_value += value
        open_cost += cost
        open_rows.append({
            "Code": code,
            "Company": names.get(code, code),
            "Shares": state["shares"],
            "Average cost": float(average),
            "Latest close": close_text,
            "Close date": close_date,
            "Value": float(value),
            "Profit / loss": float(profit),
            "Return %": float(profit / cost * 100) if cost else 0,
            "_close": close_number,
        })
    if any(row["_close"] is None for row in open_rows):
        st.caption("A holding with no official close yet is shown at the price you paid.")
    if open_rows:
        show_open = pd.DataFrame(open_rows).drop(columns=["_close"])
        st.dataframe(
            show_open.style.format({
                "Average cost": "{:,.2f}",
                "Value": "{:,.2f}",
                "Profit / loss": "{:+,.2f}",
                "Return %": "{:+.2f}%",
            }),
            use_container_width=True,
            hide_index=True,
        )
    total_profit = open_value - open_cost + realized
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        fit_stat("Shares still held", f"{sum(row['Shares'] for row in open_rows):,}")
    with m2:
        fit_stat("Cost of open shares", money(open_cost))
    with m3:
        fit_stat("Value at latest close", money(open_value))
    with m4:
        fit_stat("Profit / loss", money(total_profit), pct(float(total_profit / open_cost * 100) if open_cost else 0))
    if realized:
        st.caption(f"Profit already taken on sells: {money(realized)}. That amount is included in the profit above.")

    real_bands = []
    for code, opened, closed in held_intervals(saved, max_date):
        real_bands.append((names.get(code, code), opened, closed, None))
    show_holding_chart(
        equity_data,
        sorted({trade["code"] for trade in saved}),
        min_date,
        max_date,
        real_bands,
        "real_range",
        "Each line starts at 100 on the first date in the range. Drag the range across the dates we have. Each shaded band is the time that stock was held. A stock you still hold is shaded through the latest close.",
    )

    ledger = []
    for trade in saved:
        official = official_close(equity_data, trade["code"], trade["trade_date"])
        paid = float(trade["price"])
        ledger.append({
            "Date": trade["trade_date"].strftime("%d %b %Y"),
            "Side": trade["side"].title(),
            "Code": trade["code"],
            "Shares": trade["shares"],
            "Your price": paid,
            "Official close": "—" if official is None else f"{official:,.2f}",
            "Your price minus close": None if official is None else paid - official,
        })
    st.markdown("<div class='section-title'>Trades</div>", unsafe_allow_html=True)
    st.dataframe(
        pd.DataFrame(ledger).style.format({"Your price": "{:,.2f}", "Your price minus close": "{:+,.2f}"}, na_rep="—"),
        use_container_width=True,
        hide_index=True,
    )
    labels = {
        f"{trade['trade_date']:%d %b %Y} · {trade['side'].title()} · {trade['code']} · {trade['shares']} @ {trade['price']}": trade["id"]
        for trade in saved
    }
    remove_label = st.selectbox("Remove a trade", list(labels), key="remove_trade")
    if st.button("Remove trade"):
        remaining = [trade for trade in saved if trade["id"] != labels[remove_label]]
        _positions, remove_error = combine_trades(remaining)
        if remove_error:
            st.error(remove_error)
        else:
            PortfolioTrade.objects.filter(pk=labels[remove_label], user=user).delete()
            st.rerun()

def make_line_chart(df, x="date", y="price", color=None, title=None):
    fig = px.line(df, x=x, y=y, color=color, title=title,
                  labels={"date":"Trading date", "price":"Share price (KSh)", "display_name":"Company"})
    fig.update_layout(
        template="plotly_white", height=390, margin=dict(l=12,r=12,t=54,b=12),
        legend_title_text="", hovermode="x unified",
        title_font=dict(size=17, color="#17243b"),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="white",
        font=dict(family="Inter, Arial, sans-serif", color="#334155"),
    )
    fig.update_xaxes(showgrid=False, linecolor="#dfe6ef")
    fig.update_yaxes(gridcolor="#edf1f6", zeroline=False, tickprefix="KSh ")
    return fig

def _rgba(color, alpha=0.2):
    text = str(color or "#087f8c").strip()
    if text.startswith("rgba"):
        return text
    if text.startswith("rgb"):
        inner = text[text.find("(") + 1:text.rfind(")")]
        parts = [part.strip() for part in inner.split(",")[:3]]
        return f"rgba({','.join(parts)},{alpha})"
    hex_color = text.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(character * 2 for character in hex_color)
    red, green, blue = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return f"rgba({red},{green},{blue},{alpha})"

def shade_band(fig, start, end, color):
    if start is None or end is None or pd.Timestamp(end) < pd.Timestamp(start):
        return
    fig.add_vrect(
        x0=pd.Timestamp(start),
        x1=pd.Timestamp(end),
        fillcolor=color,
        layer="below",
        line_width=0,
    )

def price_path_chart(frame, title, bands):
    """Price lines over a chosen window. bands are (name, start, end, color)."""
    fig = px.line(
        frame, x="date", y="indexed", color="display_name", title=title,
        labels={"date": "Trading date", "indexed": "Price path (starts at 100)", "display_name": "Company"},
    )
    fig.update_layout(
        template="plotly_white", height=420, margin=dict(l=12, r=12, t=54, b=12),
        legend_title_text="", hovermode="x unified",
        title_font=dict(size=17, color="#17243b"),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="white",
        font=dict(family="Inter, Arial, sans-serif", color="#334155"),
    )
    fig.update_xaxes(showgrid=False, linecolor="#dfe6ef")
    fig.update_yaxes(gridcolor="#edf1f6", zeroline=False)
    color_by_name = {trace.name: trace.line.color for trace in fig.data}
    drawn = set()
    for name, start, end, color in bands:
        key = (name, str(start), str(end))
        if key in drawn:
            continue
        drawn.add(key)
        shade_band(fig, start, end, color or _rgba(color_by_name.get(name), 0.2))
    return fig

def show_holding_chart(equity_data, codes, min_date, max_date, bands, slider_key, caption):
    st.markdown("<div class='section-title'>Price path</div>", unsafe_allow_html=True)
    st.caption(caption)
    start_date, end_date = st.slider(
        "Graph date range",
        min_value=min_date,
        max_value=max_date,
        value=(min_date, max_date),
        format="DD MMM YYYY",
        key=slider_key,
    )
    if start_date > end_date:
        st.error("The graph start must be on or before the end.")
        return
    window = equity_data[
        equity_data["Code"].isin(list(codes))
        & (equity_data["date"].dt.date >= start_date)
        & (equity_data["date"].dt.date <= end_date)
    ].copy()
    if window.empty:
        st.info("No prices in that date range for these stocks.")
        return
    window = window.sort_values(["Code", "date"])
    window["base_price"] = window.groupby("Code")["price"].transform("first")
    window = window[window["base_price"] > 0]
    if window.empty:
        st.info("No prices in that date range for these stocks.")
        return
    window["indexed"] = window["price"] / window["base_price"] * 100
    st.plotly_chart(price_path_chart(window, "Share prices across the dates you chose", bands), use_container_width=True)

setup_django()
try:
    user = signed_in_user()
except Exception as exc:
    st.error(f"Could not reach the account database: {exc}")
    st.stop()
if user is None:
    show_login()

st.markdown("""
<div class="hero">
  <h1>📈 NSE Investment Explorer</h1>
  <p>Understand Nairobi Securities Exchange prices, compare stocks, and test what a past investment might be worth today.</p>
</div>
""", unsafe_allow_html=True)

try:
    data, _missing = load_data()
except Exception as exc:
    st.error(f"Could not load the market data: {exc}")
    st.stop()

min_date = data["date"].min().date()
max_date = data["date"].max().date()
equity_data = data[~data["Code"].astype(str).str.startswith("^")].copy()
index_data = data[data["Code"].astype(str).str.startswith("^")].copy()

with st.sidebar:
    st.markdown("## Explore")
    mode = st.radio("Workspace", ["Single stock", "Compare stocks", "Market leaderboard", "Data quality"], index=0)
    st.markdown("---")
    st.markdown("### Dataset")
    st.caption(f"{len(data):,} daily records")
    st.caption(f"{data['Code'].nunique()} symbols · {min_date:%d %b %Y} – {max_date:%d %b %Y}")
    st.caption("Prices are the dataset's `Day Price` field.")
    st.markdown("---")
    st.caption(f"Signed in as {user.username}")
    if st.button("Log out"):
        st.session_state.pop("user_id", None)
        st.rerun()
    st.markdown("---")
    st.caption("For research and education. Historical performance is not a forecast.")

if mode == "Single stock":
    symbols = sorted(equity_data["Code"].unique())
    default_symbol = "DTK" if "DTK" in symbols else ("UCHM" if "UCHM" in symbols else symbols[0])
    symbol = st.selectbox("Choose a company", symbols, index=symbols.index(default_symbol))
    hist = equity_data[equity_data["Code"] == symbol].sort_values("date").copy()
    company_name = hist["display_name"].iloc[-1]
    latest = hist.iloc[-1]
    first = hist.iloc[0]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Latest recorded price", price_fmt(latest["price"]), help=f"Last record in this dataset: {latest['date']:%d %b %Y}")
    if len(hist) > 1:
        prev = hist.iloc[-2]
        dchange = latest["price"] - prev["price"]
        dchange_pct = dchange / prev["price"] * 100 if prev["price"] else None
    else:
        dchange, dchange_pct = None, None
    c2.metric("Change vs previous record", price_fmt(dchange) if dchange is not None else "—",
              delta=pct(dchange_pct) if dchange_pct is not None else None)
    c3.metric("Lowest recorded price", price_fmt(hist["price"].min()))
    c4.metric("Highest recorded price", price_fmt(hist["price"].max()))

    st.markdown(f"<div class='section-title'>{company_name} <span class='subtle'>({symbol})</span></div>", unsafe_allow_html=True)
    st.caption(f"History available: {hist['date'].min():%d %b %Y} to {hist['date'].max():%d %b %Y}. Non-trading days are naturally absent.")
    col_a, col_b = st.columns([1.4, 1])
    with col_a:
        start_date, end_date = st.slider(
            "Chart date range", min_value=min_date, max_value=max_date,
            value=(max(hist["date"].min().date(), min_date), min(hist["date"].max().date(), max_date)),
            format="DD MMM YYYY"
        )
    with col_b:
        chart_style = st.radio("Chart view", ["Price line", "Candlestick"], horizontal=True)
    filtered = hist[(hist["date"].dt.date >= start_date) & (hist["date"].dt.date <= end_date)]
    if filtered.empty:
        st.info("No records for this date range.")
    elif chart_style == "Price line":
        st.plotly_chart(make_line_chart(filtered), use_container_width=True)
    else:
        fig = go.Figure(data=[go.Candlestick(
            x=filtered["date"], open=filtered["previous"], high=filtered["day_high"],
            low=filtered["day_low"], close=filtered["price"], name=symbol
        )])
        fig.update_layout(template="plotly_white", height=390, margin=dict(l=12,r=12,t=30,b=12),
                          paper_bgcolor="rgba(0,0,0,0)", xaxis_title="Trading date",
                          yaxis_title="Price (KSh)", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)

    earned_tab, portfolio_tab = st.tabs(["What you would have earned", "My portfolio"])
    with earned_tab:
        with st.container():
            st.markdown('<span class="invest-anchor"></span>', unsafe_allow_html=True)
            st.markdown("<div class='section-title'>What if you had invested?</div>", unsafe_allow_html=True)
            st.caption("Buy and sell at the nearest recorded close on or before each date. The sell date starts at the latest date in the data. Fees, taxes and dividends are not included.")
            default_purchase = max(min_date, min(pd.Timestamp("2024-10-28").date(), max_date))
            inv1, inv2, inv3 = st.columns(3)
            with inv1:
                investment = st.number_input("Investment amount (KSh)", min_value=100.0, value=1_000_000.0, step=50_000.0, format="%.2f", key="one_amount")
            with inv2:
                purchase_date = st.date_input("Purchase date", value=default_purchase, min_value=min_date, max_value=max_date, key="one_buy")
            with inv3:
                sell_date = st.date_input("Sell date", value=max_date, min_value=min_date, max_value=max_date, key="one_sell")
            result, reason = holding_result(hist, investment, purchase_date, sell_date)
            if result is None:
                st.warning(reason)
            else:
                r1, r2 = st.columns(2)
                with r1:
                    st.markdown(f"**Purchase price used:** {price_fmt(result['buy_price'])} · {result['buy_date']:%d %b %Y}")
                    st.markdown(f"**Sale price used:** {price_fmt(result['sell_price'])} · {result['sell_date']:%d %b %Y}")
                    st.markdown(f"**Shares bought:** {result['shares']:,}")
                with r2:
                    st.markdown(f"**Cash left over:** {money(result['cash_left'])}")
                    st.markdown(f"**Value of shares at sale:** {money(result['value'])}")
                    st.markdown(f"**Profit / loss:** {money(result['gain'])} ({pct(result['gain_pct'])})")
                st.progress(max(0.0, min(1.0, (result["gain_pct"] + 100) / 500)), text="Return visual (scale capped at +400%; loss below -100% is not possible for an unleveraged share)")

            st.markdown("<div class='section-title'>A portfolio</div>", unsafe_allow_html=True)
            st.caption("The amount is split evenly across the stocks you pick. Change the amount and the split updates. To give one stock more, move cash out of another. The total stays the same.")
            pf1, pf2, pf3 = st.columns(3)
            with pf1:
                pot = st.number_input("Amount to invest (KSh)", min_value=100.0, value=100_000.0, step=10_000.0, format="%.2f", key="pot")
            with pf2:
                portfolio_purchase = st.date_input("Purchase date", value=default_purchase, min_value=min_date, max_value=max_date, key="pf_buy")
            with pf3:
                portfolio_sell = st.date_input("Sell date", value=max_date, min_value=min_date, max_value=max_date, key="pf_sell")
            portfolio_defaults = [code for code in ["DTK", "SCOM", "EQTY", "KCB"] if code in symbols]
            if not portfolio_defaults:
                portfolio_defaults = symbols[:3]
            chosen = st.multiselect("Stocks in the mix", symbols, default=portfolio_defaults[:4], max_selections=8)
            holdings = []
            if not chosen:
                st.info("Choose at least one stock.")
            else:
                signature = (round(float(pot), 2), tuple(chosen))
                if st.session_state.get("alloc_signature") != signature:
                    for code, amount in split_amount(pot, chosen).items():
                        st.session_state[f"alloc_{code}"] = amount
                    st.session_state["alloc_signature"] = signature
                elif "pending_move" in st.session_state:
                    source, destination, moved = st.session_state.pop("pending_move")
                    source_key = f"alloc_{source}"
                    destination_key = f"alloc_{destination}"
                    available = float(st.session_state.get(source_key, 0))
                    moved = min(max(float(moved), 0), available)
                    st.session_state[source_key] = round(available - moved, 2)
                    st.session_state[destination_key] = round(float(st.session_state.get(destination_key, 0)) + moved, 2)
                alloc_cols = st.columns(min(4, len(chosen)))
                allocations = {}
                for index, code in enumerate(chosen):
                    with alloc_cols[index % 4]:
                        allocations[code] = st.number_input(
                            f"{code} (KSh)",
                            min_value=0.0,
                            step=1_000.0,
                            format="%.2f",
                            key=f"alloc_{code}",
                        )
                if len(chosen) > 1:
                    st.markdown("**Move cash**")
                    move_from, move_to, move_amt = st.columns(3)
                    with move_from:
                        take_from = st.selectbox("Take from", chosen, key="move_from")
                    destinations = [code for code in chosen if code != take_from]
                    if st.session_state.get("move_to") not in destinations:
                        st.session_state["move_to"] = destinations[0]
                    with move_to:
                        add_to = st.selectbox("Add to", destinations, key="move_to")
                    with move_amt:
                        move_amount = st.number_input("Amount to move (KSh)", min_value=0.0, step=1_000.0, format="%.2f", key="move_amount")
                    if st.button("Move", key="move_cash"):
                        available = float(allocations[take_from])
                        if move_amount <= 0:
                            st.warning("Enter an amount to move.")
                        elif move_amount > available + 0.001:
                            st.error(f"{take_from} only has {money(available)}.")
                        else:
                            st.session_state["pending_move"] = (take_from, add_to, float(move_amount))
                            st.rerun()
                allocated = sum(allocations.values())
                notes = []
                for code in chosen:
                    amount = allocations[code]
                    if amount <= 0:
                        notes.append(f"{code} has no money allocated.")
                        continue
                    series = equity_data[equity_data["Code"] == code].sort_values("date")
                    outcome, outcome_reason = holding_result(series, amount, portfolio_purchase, portfolio_sell)
                    name = series["display_name"].iloc[-1] if not series.empty else code
                    if outcome is None:
                        notes.append(f"{code}: {outcome_reason}")
                        continue
                    holdings.append({"Code": code, "Company": name, "Amount": amount, **outcome})
                unallocated = pot - allocated
                if allocated > pot + 0.01:
                    st.warning(f"The mix adds up to {money(allocated)}, which is {money(allocated - pot)} more than the pot.")
                elif unallocated > 0.01:
                    st.caption(f"Allocated {money(allocated)}. {money(unallocated)} of the pot is still unallocated cash.")
                if notes:
                    st.warning(" ".join(notes))
                if holdings:
                    table = pd.DataFrame(holdings)
                    table = table.sort_values(["gain", "gain_pct"], ascending=False)
                    table.insert(0, "Rank", range(1, len(table) + 1))
                    show_table = table.rename(columns={
                        "buy_price": "Buy price",
                        "sell_price": "Sell price",
                        "buy_date": "Bought",
                        "sell_date": "Sold",
                        "shares": "Shares",
                        "cash_left": "Cash left",
                        "value": "Share value",
                        "gain": "Profit / loss",
                        "gain_pct": "Return %",
                    })
                    show_table["Bought"] = pd.to_datetime(show_table["Bought"]).dt.strftime("%d %b %Y")
                    show_table["Sold"] = pd.to_datetime(show_table["Sold"]).dt.strftime("%d %b %Y")
                    show_table = show_table[["Rank", "Code", "Company", "Amount", "Shares", "Bought", "Buy price", "Sold", "Sell price", "Share value", "Cash left", "Profit / loss", "Return %"]]
                    st.dataframe(
                        show_table.style.format({
                            "Amount": "{:,.2f}",
                            "Buy price": "{:,.2f}",
                            "Sell price": "{:,.2f}",
                            "Share value": "{:,.2f}",
                            "Cash left": "{:,.2f}",
                            "Profit / loss": "{:+,.2f}",
                            "Return %": "{:+.2f}%",
                        }),
                        use_container_width=True,
                        hide_index=True,
                    )
                    share_value = float(table["value"].sum())
                    rounding_cash = float(table["cash_left"].sum())
                    placed = float(table["Amount"].sum())
                    unplaced = allocated - placed
                    cash_held = rounding_cash + unplaced + max(unallocated, 0)
                    wealth = share_value + cash_held
                    basis = pot if unallocated >= -0.01 else allocated
                    gain = wealth - basis
                    gain_pct = (gain / basis * 100) if basis else 0
                    t1, t2, t3, t4 = st.columns(4)
                    with t1:
                        fit_stat("Spent on shares", money(placed - rounding_cash))
                    with t2:
                        fit_stat("Cash still held", money(cash_held))
                    with t3:
                        fit_stat("Wealth at sale", money(wealth))
                    with t4:
                        fit_stat("Portfolio profit / loss", money(gain), pct(gain_pct))
                    rank_chart = table.sort_values("gain_pct")
                    fig = px.bar(
                        rank_chart, x="gain_pct", y="Code", orientation="h",
                        hover_data=["Company", "gain"],
                        labels={"gain_pct": "Return (%)", "Code": ""},
                        title="Ranked by return",
                    )
                    fig.update_layout(
                        template="plotly_white", height=max(220, 46 * len(rank_chart) + 80),
                        margin=dict(l=8, r=8, t=48, b=8), paper_bgcolor="rgba(0,0,0,0)",
                        title_font=dict(size=16, color="#17243b"),
                    )
                    fig.update_xaxes(ticksuffix="%", gridcolor="#edf1f6")
                    st.plotly_chart(fig, use_container_width=True)
                estimate_bands = []
                if portfolio_sell >= portfolio_purchase:
                    estimate_bands = [("Held", portfolio_purchase, portfolio_sell, "rgba(8,127,140,0.22)")]
                show_holding_chart(
                    equity_data,
                    chosen,
                    min_date,
                    max_date,
                    estimate_bands,
                    "estimate_range",
                    "Each line starts at 100 on the first date in the range. Drag the range across the dates we have. The shaded band is the purchase date through the sell date.",
                )
        with st.expander("How to read this"):
            st.markdown("""
- **Latest recorded price** is the last date present in your files, not a live market quote.
- **Change vs previous record** compares the last row with the previous row for that company.
- **Purchase date** and **sell date** each use the nearest recorded close on or before that day. The sell date starts at the latest date in the data.
- Shares are bought in whole shares. Cash that cannot buy another share is still cash, so it is not a loss.
- Changing the portfolio amount splits it evenly across the chosen stocks. Move cash takes money from one stock and adds the same amount to another.
- Dividends and corporate actions are not included because the supplied `Adjusted Price` column is entirely `-`.
""")
    with portfolio_tab:
        render_portfolio(user, equity_data, symbols, min_date, max_date)
    with st.expander("View recent records"):
        show = filtered.tail(50)[["date","Code","display_name","price","day_low","day_high","volume"]].copy()
        show.columns = ["Date","Code","Company","Day price (KSh)","Day low","Day high","Volume"]
        st.dataframe(show.sort_values("Date", ascending=False), use_container_width=True, hide_index=True)

elif mode == "Compare stocks":
    symbols = sorted(equity_data["Code"].unique())
    defaults = [x for x in ["DTK", "SCOM", "EQTY", "UCHM"] if x in symbols]
    selected = st.multiselect("Select up to 6 stocks", symbols, default=defaults[:4], max_selections=6)
    col1, col2 = st.columns(2)
    with col1:
        compare_start = st.date_input("Start date", value=max(min_date, pd.Timestamp("2024-01-02").date()), min_value=min_date, max_value=max_date, key="cmpstart")
    with col2:
        compare_end = st.date_input("End date", value=max_date, min_value=min_date, max_value=max_date, key="cmpend")
    if compare_start > compare_end:
        st.error("Start date must be on or before end date.")
    elif not selected:
        st.info("Choose at least one stock to compare.")
    else:
        sliced = equity_data[(equity_data["Code"].isin(selected)) &
                             (equity_data["date"].dt.date >= compare_start) &
                             (equity_data["date"].dt.date <= compare_end)].copy()
        # Normalize each series to 100 at its first available record in range.
        sliced["base_price"] = sliced.groupby("Code")["price"].transform("first")
        sliced["indexed_value"] = sliced["price"] / sliced["base_price"] * 100
        if sliced.empty:
            st.warning("No records found for the selected stocks and dates.")
        else:
            fig = px.line(sliced, x="date", y="indexed_value", color="display_name",
                          labels={"date":"Trading date","indexed_value":"Growth of KSh 100 (index)","display_name":"Company"},
                          title="Relative performance (each stock starts at 100)")
            fig.update_layout(template="plotly_white", height=470, hovermode="x unified",
                              paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="white",
                              margin=dict(l=10,r=10,t=55,b=10), legend_title_text="")
            fig.update_yaxes(gridcolor="#edf1f6", ticksuffix="")
            st.plotly_chart(fig, use_container_width=True)
            summaries = []
            for s in selected:
                h = sliced[sliced["Code"] == s].sort_values("date")
                if h.empty: continue
                startp, endp = h["price"].iloc[0], h["price"].iloc[-1]
                summaries.append({"Code":s,"Company":h["display_name"].iloc[-1],
                                  "First date":h["date"].iloc[0].date(),
                                  "Start price (KSh)":startp,"Last date":h["date"].iloc[-1].date(),
                                  "End price (KSh)":endp,"Price return (%)":(endp/startp-1)*100})
            summary = pd.DataFrame(summaries).sort_values("Price return (%)", ascending=False)
            st.dataframe(summary.style.format({"Start price (KSh)":"{:,.3f}","End price (KSh)":"{:,.3f}","Price return (%)":"{:+.2f}%"}),
                         use_container_width=True, hide_index=True)
            st.caption("This comparison normalizes each share to 100 at its first available price in the selected window. It compares price performance only, not dividends or risk.")

elif mode == "Market leaderboard":
    st.markdown("<div class='section-title'>Historical price movers</div>", unsafe_allow_html=True)
    st.caption("Ranks listed companies by change in recorded share price between the first and last available records in the selected period. It is not a live recommendation.")
    l1, l2, l3 = st.columns([1,1,1])
    with l1:
        rank_start = st.date_input("From", value=max(min_date, pd.Timestamp("2024-01-02").date()), min_value=min_date, max_value=max_date, key="rankstart")
    with l2:
        rank_end = st.date_input("To", value=max_date, min_value=min_date, max_value=max_date, key="rankend")
    with l3:
        rank_type = st.selectbox("Rank", ["Top gainers", "Top decliners", "All companies"], index=0)
    if rank_start > rank_end:
        st.error("Start date must be on or before end date.")
    else:
        sliced = equity_data[(equity_data["date"].dt.date >= rank_start) & (equity_data["date"].dt.date <= rank_end)]
        rows = []
        for code, h in sliced.groupby("Code"):
            h = h.sort_values("date")
            if len(h) < 2: continue
            p0, p1 = h["price"].iloc[0], h["price"].iloc[-1]
            rows.append({"Code":code,"Company":h["display_name"].iloc[-1],
                         "Start date":h["date"].iloc[0].date(),"Start price":p0,
                         "End date":h["date"].iloc[-1].date(),"End price":p1,
                         "Return (%)":(p1/p0-1)*100,"Records":len(h)})
        rankdf = pd.DataFrame(rows)
        if rankdf.empty:
            st.info("Not enough data in the selected period.")
        else:
            if rank_type == "Top gainers":
                rankdf = rankdf.sort_values("Return (%)", ascending=False).head(15)
            elif rank_type == "Top decliners":
                rankdf = rankdf.sort_values("Return (%)", ascending=True).head(15)
            else:
                rankdf = rankdf.sort_values("Return (%)", ascending=False)
            fig = px.bar(rankdf.sort_values("Return (%)"), x="Return (%)", y="Company", orientation="h",
                         hover_data=["Code","Start price","End price","Records"],
                         title="Share-price return over selected period",
                         labels={"Return (%)":"Price return (%)","Company":""})
            fig.update_layout(template="plotly_white", height=max(380, min(780, len(rankdf)*30)),
                              margin=dict(l=10,r=10,t=55,b=10), paper_bgcolor="rgba(0,0,0,0)")
            fig.update_xaxes(ticksuffix="%", gridcolor="#edf1f6")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(rankdf.style.format({"Start price":"{:,.3f}","End price":"{:,.3f}","Return (%)":"{:+.2f}%"}),
                         use_container_width=True, hide_index=True)
            st.warning("A large percentage gain can come from a very low starting price or thin trading. Check trading volume and the underlying company before drawing conclusions.")

elif mode == "Data quality":
    st.markdown("<div class='section-title'>Data coverage & checks</div>", unsafe_allow_html=True)
    stats1, stats2, stats3, stats4 = st.columns(4)
    stats1.metric("Rows loaded", f"{len(data):,}")
    stats2.metric("Symbols", f"{data['Code'].nunique():,}")
    stats3.metric("First date", data["date"].min().strftime("%d %b %Y"))
    stats4.metric("Last date", data["date"].max().strftime("%d %b %Y"))
    quality = data.groupby(data["date"].dt.year).agg(
        Records=("Code","size"), Symbols=("Code","nunique"),
        Trading_days=("date","nunique"), Missing_prices=("price",lambda s:s.isna().sum()),
        Missing_volumes=("volume",lambda s:s.isna().sum())
    ).reset_index(names="Year")
    st.markdown("#### Coverage by year")
    st.dataframe(quality, use_container_width=True, hide_index=True)
    st.markdown("#### Important limitations")
    st.markdown("""
- History is loaded from Postgres. The yearly CSV files and one CSV per month are imported when the stack starts, and each new session close is appended to that month's file.
- The supplied `Adjusted Price` field is `-` for every row. Dividend-inclusive or corporate-action-adjusted total returns cannot be calculated from these files alone.
- `Volume` uses `-` for unavailable/no reported volume; this should not automatically be treated as zero.
- The files contain both listed companies and market indices. Codes beginning with `^` are excluded from the stock picker and leaderboard.
- A company can change its display name while retaining a ticker, and symbols may enter or leave the data over time.
- The app uses `Day Price` as the recorded price. Validate the source's definition of that field before treating it as an official closing price.
""")
    st.markdown("#### Symbols with multiple recorded names")
    variations = data.groupby("Code")["Name"].nunique()
    changed = variations[variations > 1].index.tolist()
    if changed:
        varrows = []
        for code in changed:
            names = sorted(data.loc[data["Code"] == code, "Name"].dropna().unique().tolist())
            varrows.append({"Code":code,"Recorded names":" · ".join(names)})
        st.dataframe(pd.DataFrame(varrows), use_container_width=True, hide_index=True)
    else:
        st.success("No ticker name variations found.")
    st.markdown("#### Download cleaned dataset")
    export = data[["date","Code","display_name","price","day_low","day_high","previous","change","change_pct","volume"]].copy()
    export.columns = ["date","code","company","day_price_ksh","day_low_ksh","day_high_ksh","previous_ksh","change_ksh","change_pct","volume"]
    st.download_button("Download cleaned CSV", export.to_csv(index=False).encode("utf-8"), "nse_cleaned_history.csv", "text/csv")

st.markdown("---")
st.caption(f"NSE Investment Explorer · Prices through {max_date:%d %b %Y}. Not investment advice.")
