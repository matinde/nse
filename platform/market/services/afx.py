import re
import socket
from datetime import datetime
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
NAIROBI = ZoneInfo("Africa/Nairobi")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class BoardParseError(Exception):
    pass


class SessionNotClosed(Exception):
    pass


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
