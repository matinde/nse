import re
import socket
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import requests
import urllib3.util.connection as urllib3_connection

# The board publishes IPv6 addresses first. The container has no IPv6 route,
# so connect() fails with ENETUNREACH and the close is never saved.
urllib3_connection.allowed_gai_family = lambda: socket.AF_INET

from market.services.rows import PriceRow, parse_date, parse_num, parse_volume

BOARD_URL = "https://afx.kwayisi.org/nse/"
HISTORY_URL = "https://afx.kwayisi.org/nse/{code}.html"
NSE_STATS_PAGE = "https://www.nse.co.ke/dataservices/market-statistics/"
NSE_AJAX_URL = "https://www.nse.co.ke/dataservices/wp-admin/admin-ajax.php"
NSE_SECTORS = (
    "agric",
    "auto",
    "bank",
    "comm",
    "const",
    "energy",
    "insr",
    "invest",
    "investse",
    "manu",
    "tele",
    "real",
    "exchange",
)
# Official equity list is published by sector, with an ISIN and no ticker.
ISIN_TO_CODE = {
    "KE0000000281": "KUKZ",
    "KE0000000430": "SASN",
    "KE0000000208": "EGAD",
    "KE0000000505": "WTK",
    "KE4000001760": "KAPC",
    "KE0000000356": "LIMT",
    "KE0000000109": "CGEN",
    "KE0000000091": "SBIC",
    "KE0000000158": "DTK",
    "KE0000000554": "EQTY",
    "KE0000000315": "KCB",
    "KE0000000398": "NBK",
    "KE0000000406": "NCBA",
    "KE0000000448": "SCBK",
    "KE1000001568": "COOP",
    "KE0000000125": "IMH",
    "KE5000008986": "BKG",
    "KE0000000067": "ABSA",
    "KE9930006987": "FMLY",
    "KE0000000240": "HFCK",
    "KE0000000224": "XPRS",
    "KE0000000307": "KQ",
    "KE0000000380": "NMG",
    "KE0000000562": "SCAN",
    "KE0000000455": "SGL",
    "KE0000000539": "TPSE",
    "KE0000000489": "UCHM",
    "KE0000000588": "EVRD",
    "KE0000000232": "SMER",
    "KE2000002275": "LKL",
    "KE5000005438": "DCON",
    "KE5000000090": "NBV",
    "KE7000001433": "HBE",
    "KE0000000034": "ARM",
    "KE0000000059": "BAMB",
    "KE0000000141": "CRWN",
    "KE0000000174": "CABL",
    "KE0000000190": "PORT",
    "UG0000001145": "UMME",
    "KE0000000547": "KEGN",
    "KE0000000349": "KPLC",
    "KE0000000463": "TOTL",
    "KE9900006215": "KPC",
    "KE0000000273": "JUB",
    "KE0000000604": "KNRE",
    "KE0000000414": "SLAM",
    "KE2000002317": "CIC",
    "KE2000002168": "LBTY",
    "KE2000002192": "BRIT",
    "KE4000001216": "KURV",
    "KE0000000265": "CTUM",
    "KE0000000166": "OCH",
    "KE2000007258": "HAFR",
    "KE2000002184": "TCL",
    "KE3000009674": "NSE",
    "KE0000000331": "AMAC",
    "KE0000000042": "BOC",
    "KE0000000075": "BAT",
    "KE0000000117": "CARB",
    "KE0000000216": "EABL",
    "KE0000000372": "MSC",
    "KE0000000497": "UNGA",
    "KE4000001323": "FTGH",
    "KE9900001216": "SKL",
    "KE1000001402": "SCOM",
    "KE9100008870": "LAPR",
    "KE9900006322": "ALP",
    "KE9930007092": "TRFC",
    "ZAE000060067": "GLD",
    "ZAE000246104": "SMWF",
}
NAIROBI = ZoneInfo("Africa/Nairobi")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class BoardParseError(Exception):
    pass


class SessionNotClosed(Exception):
    pass


def fetch_nse_board():
    """Latest closes from the NSE market-statistics sector tables."""
    page = requests.get(NSE_STATS_PAGE, headers={"User-Agent": USER_AGENT}, timeout=30)
    page.raise_for_status()
    nonce_match = re.search(r'"ajaxnonce":"([a-f0-9]+)"', page.text)
    if nonce_match is None:
        raise BoardParseError("The NSE statistics page did not include a sector key.")
    nonce = nonce_match.group(1)
    session_date = None
    quotes = []
    seen = set()
    for sector in NSE_SECTORS:
        response = requests.post(
            NSE_AJAX_URL,
            data={"action": "display_prices", "security": nonce, "sector": sector},
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        )
        response.raise_for_status()
        html = response.text
        if session_date is None:
            dated = re.search(r"Statistics as of (\d{1,2}-[A-Za-z]{3}-\d{4})", html)
            if dated:
                session_date = parse_date(dated.group(1))
        for name, isin, volume_text, price_text, change_text in _sector_rows(html):
            code = ISIN_TO_CODE.get(isin.upper())
            price = parse_num(price_text)
            if code is None or code in seen or price is None or price <= 0:
                continue
            seen.add(code)
            change_pct = parse_num(change_text)
            volume = parse_volume(volume_text)
            short_name = _company_name(name)
            quotes.append(
                PriceRow(
                    trade_date=date.min,
                    code=code,
                    name=short_name,
                    day_price=price,
                    change_pct=change_pct,
                    volume=volume,
                    price_text=price_text.strip(),
                    change_pct_text=change_text.strip(),
                    volume_text=volume_text.strip(),
                )
            )
    if session_date is None:
        raise BoardParseError("The NSE sector tables did not include a session date.")
    now = datetime.now(NAIROBI)
    if session_date == now.date() and (now.hour, now.minute) < (15, 30):
        raise SessionNotClosed(f"Nairobi time is {now:%H:%M}, before the 15:30 close.")
    if not quotes:
        raise BoardParseError("The NSE sector tables did not contain any prices.")
    for row in quotes:
        row.trade_date = session_date
    return session_date, quotes


def _sector_rows(html: str):
    return re.findall(
        r"<tr><td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td[^>]*><span>([^<]+)",
        html,
        flags=re.S,
    )


def _company_name(name: str) -> str:
    text = " ".join(name.split())
    text = re.sub(r"\s+(?:Ord|0rd)\b.*$", "", text, flags=re.I)
    return text.strip() or name.strip()


def fetch_html(url: str, session: requests.Session | None = None) -> str:
    client = session or requests
    response = client.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()
    return response.text


def parse_board(html: str):
    observed = _clock(html)
    local = observed.astimezone(NAIROBI)
    if (local.hour, local.minute) < (15, 30):
        raise SessionNotClosed(
            f"Board clock is {local:%H:%M} Africa/Nairobi, before the 15:30 close."
        )

    table = re.search(r"<th>Ticker.*?</table>", html, flags=re.I | re.S)
    if table is None:
        raise BoardParseError("The NSE board page has no listings table.")
    quotes = []
    for cells in _table_rows(table.group(0)):
        if len(cells) < 5:
            continue
        code = cells[0].strip().upper()
        if not code or code.startswith("^"):
            continue
        price_text = cells[3].strip()
        price = parse_num(price_text)
        if price is None:
            continue
        name = cells[1].strip() or code
        volume_text = cells[2].replace(",", "").strip()
        change_text = cells[4].replace(",", "").strip().lstrip("+")
        change = parse_num(change_text)
        previous = price - change if change is not None else None
        change_pct = None
        if previous not in (None, Decimal("0")) and change is not None:
            change_pct = (change / previous) * Decimal("100")
        quotes.append(
            PriceRow(
                trade_date=local.date(),
                code=code,
                name=name,
                day_price=price,
                previous=previous,
                change=change,
                change_pct=change_pct,
                volume=parse_volume(volume_text),
                price_text=price_text,
                previous_text="" if previous is None else _plain(previous),
                change_text=change_text,
                change_pct_text="" if change_pct is None else f"{change_pct:.2f}%",
                volume_text=volume_text,
            )
        )
    if not quotes:
        raise BoardParseError("The NSE board page did not contain any prices.")
    return local.date(), quotes


def parse_history(html: str, code: str, name: str) -> list[PriceRow]:
    rows = []
    seen = set()
    for table in re.findall(r"<table\b.*?</table>", html, flags=re.I | re.S):
        for cells in _table_rows(table):
            if len(cells) < 3:
                continue
            trade_date = parse_date(cells[0])
            if trade_date is None or trade_date in seen:
                continue
            price_text = cells[2].strip()
            price = parse_num(price_text)
            if price is None:
                continue
            seen.add(trade_date)
            volume_text = cells[1].replace(",", "").strip()
            change_text = cells[3].replace(",", "").strip().lstrip("+") if len(cells) > 3 else ""
            pct_text = cells[4].strip().lstrip("+") if len(cells) > 4 else ""
            change = parse_num(change_text)
            change_pct = parse_num(pct_text)
            previous = price - change if change is not None else None
            rows.append(
                PriceRow(
                    trade_date=trade_date,
                    code=code,
                    name=name,
                    day_price=price,
                    previous=previous,
                    change=change,
                    change_pct=change_pct,
                    volume=parse_volume(volume_text),
                    price_text=price_text,
                    previous_text="" if previous is None else _plain(previous),
                    change_text=change_text,
                    change_pct_text=pct_text,
                    volume_text=volume_text,
                )
            )
    return rows


def _clock(html: str) -> datetime:
    match = re.search(r"<time\b[^>]*\bdatetime=([^\s>]+)", html, flags=re.I)
    if match is None:
        raise BoardParseError("The NSE board page has no session clock.")
    raw = match.group(1).strip("\"'")
    observed = datetime.fromisoformat(raw)
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=NAIROBI)
    return observed


def _table_rows(table_html: str) -> list[list[str]]:
    rows = []
    for part in re.split(r"<tr\b", table_html, flags=re.I)[1:]:
        cells = re.findall(
            r"<td\b[^>]*>(.*?)(?=<td\b|<tr\b|</tr>|</table>|$)",
            part,
            flags=re.I | re.S,
        )
        if cells:
            rows.append([_strip(cell) for cell in cells])
    return rows


def _strip(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", " ", fragment)
    return " ".join(text.replace("&amp;", "&").split())


def _plain(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text
