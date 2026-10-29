import os

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
div[data-testid="stTabs"] button { font-weight:650; }
div[data-testid="stAlert"] { border-radius:12px; }
</style>
""", unsafe_allow_html=True)

def database_url():
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Start the stack with docker compose so the explorer can read Postgres."
        )
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and "+psycopg" not in url.split("://", 1)[0]:
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


@st.cache_data(show_spinner="Loading NSE price history…", ttl=300)
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

def nearest_on_or_before(history, date):
    before = history[history["date"] <= pd.Timestamp(date)]
    if before.empty:
        return None
    return before.iloc[-1]

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

    st.markdown("<div class='section-title'>What if you had invested?</div>", unsafe_allow_html=True)
    st.caption("Uses the nearest available trading record on or before the chosen purchase date, and the latest recorded price in the dataset. Fees, taxes and dividends are not included.")
    inv1, inv2 = st.columns([1, 1])
    with inv1:
        investment = st.number_input("Investment amount (KSh)", min_value=100.0, value=1_000_000.0, step=50_000.0, format="%.2f")
        purchase_date = st.date_input("Purchase date", value=max(min_date, min(pd.Timestamp("2024-10-28").date(), max_date)), min_value=min_date, max_value=max_date)
    buy = nearest_on_or_before(hist, purchase_date)
    with inv2:
        if buy is None:
            st.warning("There is no price record on or before that date for this stock.")
        else:
            shares = int(investment // buy["price"]) if buy["price"] > 0 else 0
            cash_left = investment - shares * buy["price"]
            value_now = shares * latest["price"]
            gain = value_now - investment
            gain_pct = (value_now / investment - 1) * 100 if investment else 0
            st.markdown(f"**Purchase price used:** {price_fmt(buy['price'])} · {buy['date']:%d %b %Y}")
            st.markdown(f"**Shares bought:** {shares:,}")
            st.markdown(f"**Cash left over:** {money(cash_left)}")
            st.markdown(f"**Value at latest price:** {money(value_now)}")
            st.markdown(f"**Profit / loss:** {money(gain)} ({pct(gain_pct)})")
            st.progress(max(0.0, min(1.0, (gain_pct + 100) / 500)), text="Return visual (scale capped at +400%; loss below -100% is not possible for an unleveraged share)")
    with st.expander("How to read this"):
        st.markdown("""
- **Latest recorded price** is the last date present in your files, not a live market quote.
- **Change vs previous record** compares the last row with the previous row for that company.
- **Investment value** assumes whole shares only; unused cash is not invested.
- **Profit/loss** is measured against the full amount you entered, so leftover cash is conservatively treated as part of the investment principal.
- Dividends and corporate actions are not included because the supplied `Adjusted Price` column is entirely `-`.
""")
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
