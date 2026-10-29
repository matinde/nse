import time
from datetime import date

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from market.models import DailyPrice, IngestRun, Symbol
from market.services.afx import (
    BOARD_URL,
    HISTORY_URL,
    BoardParseError,
    SessionNotClosed,
    fetch_html,
    parse_board,
    parse_history,
)
from market.services.csv_import import load_price_rows
from market.services.month_csv import append_rows
from market.services.rows import PriceRow, parse_date


def import_csvs() -> int:
    run = IngestRun.objects.create(kind=IngestRun.KIND_CSV)
    try:
        rows = load_price_rows()
        written = upsert_prices(rows, DailyPrice.SOURCE_CSV)
    except Exception as exc:
        _finish(run, IngestRun.STATUS_FAILED, 0, str(exc))
        raise
    _finish(run, IngestRun.STATUS_SUCCESS, written, "")
    return written


def fetch_session_closes() -> int:
    try:
        html = fetch_html(BOARD_URL)
        session_date, quotes = parse_board(html)
    except SessionNotClosed:
        raise
    except BoardParseError as exc:
        run = IngestRun.objects.create(kind=IngestRun.KIND_BOARD)
        _finish(run, IngestRun.STATUS_FAILED, 0, str(exc))
        raise

    run = IngestRun.objects.create(kind=IngestRun.KIND_BOARD)
    warnings: list[str] = []
    written = 0
    try:
        live_start = parse_date(settings.LIVE_FEED_START)
        if session_date < live_start:
            _finish(run, IngestRun.STATUS_SUCCESS, 0, "Session date is before the live feed.")
            return 0
        latest = (
            DailyPrice.objects.filter(trade_date__gte=live_start)
            .order_by("-trade_date")
            .values_list("trade_date", flat=True)
            .first()
        )
        grouped: dict[date, list[PriceRow]] = {}
        if latest is not None and (session_date - latest).days > 1:
            grouped, warnings = _catch_up(quotes, latest, session_date, live_start)
        grouped.setdefault(session_date, [])
        grouped[session_date].extend(quotes)

        written = 0
        for trade_date in sorted(grouped):
            written += _store_new_rows(trade_date, grouped[trade_date])
    except Exception as exc:
        _finish(run, IngestRun.STATUS_FAILED, written, str(exc))
        raise
    _finish(run, IngestRun.STATUS_SUCCESS, written, "\n".join(warnings))
    return written


def upsert_prices(rows: list[PriceRow], source: str) -> int:
    if not rows:
        return 0
    symbols = _ensure_symbols(rows)
    fetched_at = timezone.now()
    objects = [
        DailyPrice(
            symbol=symbols[row.code],
            trade_date=row.trade_date,
            recorded_name=row.name,
            day_price=row.day_price,
            previous=row.previous,
            change=row.change,
            change_pct=row.change_pct,
            volume=row.volume,
            day_low=row.day_low,
            day_high=row.day_high,
            source=source,
            fetched_at=fetched_at,
        )
        for row in rows
    ]
    written = 0
    with transaction.atomic():
        for start in range(0, len(objects), 2000):
            batch = objects[start : start + 2000]
            DailyPrice.objects.bulk_create(
                batch,
                update_conflicts=True,
                unique_fields=["symbol", "trade_date"],
                update_fields=[
                    "recorded_name",
                    "day_price",
                    "previous",
                    "change",
                    "change_pct",
                    "volume",
                    "day_low",
                    "day_high",
                    "source",
                    "fetched_at",
                ],
            )
            written += len(batch)
    return written


def _store_new_rows(trade_date: date, rows: list[PriceRow]) -> int:
    from market.services.month_csv import existing_keys, month_path

    data_dir = settings.DATA_DIR
    present = existing_keys(month_path(data_dir, trade_date))
    fresh = []
    seen = set()
    for row in rows:
        key = (trade_date, row.code)
        if key in present or key in seen:
            continue
        seen.add(key)
        fresh.append(row)
    if not fresh:
        return 0
    written = upsert_prices(fresh, DailyPrice.SOURCE_BOARD)
    append_rows(data_dir, trade_date, fresh)
    return written


def _catch_up(quotes: list[PriceRow], latest: date, session_date: date, live_start: date):
    grouped: dict[date, list[PriceRow]] = {}
    warnings = []
    session = requests.Session()
    for quote in quotes:
        url = HISTORY_URL.format(code=quote.code.lower())
        try:
            html = fetch_html(url, session)
        except requests.RequestException as exc:
            warnings.append(f"{quote.code}: {exc}")
            time.sleep(0.3)
            continue
        for row in parse_history(html, quote.code, quote.name):
            if row.trade_date <= latest or row.trade_date >= session_date or row.trade_date < live_start:
                continue
            grouped.setdefault(row.trade_date, []).append(row)
        time.sleep(0.3)
    return grouped, warnings


def _ensure_symbols(rows: list[PriceRow]) -> dict[str, Symbol]:
    latest_name: dict[str, tuple[date, str]] = {}
    for row in rows:
        current = latest_name.get(row.code)
        if current is None or row.trade_date >= current[0]:
            latest_name[row.code] = (row.trade_date, row.name or row.code)
    existing = {symbol.code: symbol for symbol in Symbol.objects.filter(code__in=latest_name)}
    created = []
    updated = []
    for code, (_, name) in latest_name.items():
        is_index = code.startswith("^")
        symbol = existing.get(code)
        if symbol is None:
            symbol = Symbol(code=code, name=name, is_index=is_index)
            created.append(symbol)
            existing[code] = symbol
        elif symbol.name != name or symbol.is_index != is_index:
            symbol.name = name
            symbol.is_index = is_index
            updated.append(symbol)
    if created:
        Symbol.objects.bulk_create(created)
        existing = {symbol.code: symbol for symbol in Symbol.objects.filter(code__in=latest_name)}
    if updated:
        Symbol.objects.bulk_update(updated, ["name", "is_index"])
    return existing


def _finish(run: IngestRun, status: str, rows_written: int, error: str):
    run.status = status
    run.rows_written = rows_written
    run.error = error
    run.finished_at = timezone.now()
    run.save(update_fields=["status", "rows_written", "error", "finished_at"])
