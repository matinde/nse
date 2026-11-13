from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from market.models import DailyPrice, IngestRun, PendingListing, Symbol
from market.services.afx import (
    HISTORY_URL,
    ISIN_TO_CODE,
    NAIROBI,
    BoardParseError,
    fetch_html,
    fetch_nse_board,
    parse_history,
)
from market.services.csv_import import load_price_rows, merge_missing_seed_rows, read_price_file
from market.services.month_csv import append_rows, existing_keys, month_path
from market.services.rows import PriceRow, month_file_sort_key, parse_date


def import_csvs() -> int:
    run = IngestRun.objects.create(kind=IngestRun.KIND_CSV)
    try:
        merge_missing_seed_rows()
        rows = load_price_rows()
        written = upsert_prices(rows, DailyPrice.SOURCE_CSV)
    except Exception as exc:
        _finish(run, IngestRun.STATUS_FAILED, 0, str(exc))
        raise
    _finish(run, IngestRun.STATUS_SUCCESS, written, "")
    return written


def fetch_session_closes() -> int:
    try:
        session_date, quotes, unmapped = fetch_nse_board(_isin_to_code())
    except BoardParseError as exc:
        run = IngestRun.objects.create(kind=IngestRun.KIND_BOARD)
        _finish(run, IngestRun.STATUS_FAILED, 0, str(exc))
        raise

    run = IngestRun.objects.create(kind=IngestRun.KIND_BOARD)
    written = 0
    try:
        if session_date is not None:
            live_start = parse_date(settings.LIVE_FEED_START)
            if session_date < live_start:
                _save_unmapped(session_date, unmapped)
                _finish(run, IngestRun.STATUS_SUCCESS, written, "Session date is before the live feed.")
                return written
            written += _store_new_rows(session_date, quotes)
            _save_unmapped(session_date, unmapped)
    except Exception as exc:
        _finish(run, IngestRun.STATUS_FAILED, written, str(exc))
        raise
    _finish(run, IngestRun.STATUS_SUCCESS, written, "")
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
    if written:
        cache.delete("nse-equity-frame-v2")
    return written


def closed_session_date(now: datetime | None = None) -> date:
    """Last session whose close is allowed into the files."""
    moment = now or datetime.now(NAIROBI)
    if (moment.hour, moment.minute) < (15, 30):
        return moment.date() - timedelta(days=1)
    return moment.date()


def fill_missing_closes(data_dir: Path | None = None) -> list[PriceRow]:
    """Add sessions the daily board missed.

    The statistics page only publishes the latest session. A few days offline
    used to leave a hole through the previous close, so the price path stopped
    early. Recent history pages still have those sessions.
    """
    root = Path(data_dir or settings.DATA_DIR)
    last_seen = _last_sessions(root)
    if not last_seen:
        return []
    through = closed_session_date()
    newest = max(seen for seen, _name in last_seen.values())
    cutoff = newest - timedelta(days=21)
    behind = {
        code: (seen, name)
        for code, (seen, name) in last_seen.items()
        if cutoff <= seen < through
    }
    if not behind:
        return []
    fresh: list[PriceRow] = []
    client = requests.Session()
    for code, (seen, name) in sorted(behind.items()):
        try:
            html = fetch_html(HISTORY_URL.format(code=code.lower()), client)
        except requests.RequestException:
            continue
        for row in parse_history(html, code, name):
            if seen < row.trade_date <= through:
                fresh.append(row)
    return _append_absent(fresh, root)


def _append_absent(rows: list[PriceRow], data_dir: Path | None = None) -> list[PriceRow]:
    """Append rows that are not already in that session's month file."""
    if not rows:
        return []
    root = Path(data_dir or settings.DATA_DIR)
    added: list[PriceRow] = []
    by_date: dict[date, list[PriceRow]] = {}
    for row in rows:
        by_date.setdefault(row.trade_date, []).append(row)
    for trade_date in sorted(by_date):
        present = existing_keys(month_path(root, trade_date))
        batch = []
        seen_codes = set()
        for row in by_date[trade_date]:
            if row.code in seen_codes or (trade_date, row.code) in present:
                continue
            seen_codes.add(row.code)
            batch.append(row)
        if not batch:
            continue
        append_rows(root, trade_date, batch)
        added.extend(batch)
    return added


def backfill_symbol_history(code: str) -> int:
    """Store the latest NSE session for one ticker.

    The NSE statistics tables publish the current session only.
    """
    session_date, quotes, unmapped = fetch_nse_board(_isin_to_code())
    chosen = [row for row in quotes if row.code == code]
    if not chosen:
        raise LookupError(f"{code} is not on the NSE sector tables for {session_date}.")
    live_start = parse_date(settings.LIVE_FEED_START)
    if session_date < live_start:
        raise LookupError("Session date is before the live feed.")
    _save_unmapped(session_date, unmapped)
    return _store_new_rows(session_date, chosen)


def _last_sessions(data_dir: Path) -> dict[str, tuple[date, str]]:
    found: dict[str, tuple[date, str]] = {}
    paths = sorted(data_dir.glob("NSE_*_prices.csv"), key=lambda path: month_file_sort_key(path.name))
    for path in paths:
        for row in read_price_file(path):
            current = found.get(row.code)
            if current is None or row.trade_date >= current[0]:
                found[row.code] = (row.trade_date, row.name or row.code)
    return found


def _store_new_rows(trade_date: date, rows: list[PriceRow]) -> int:
    from market.services.month_csv import existing_keys, month_path, update_session_rows

    data_dir = settings.DATA_DIR
    present = existing_keys(month_path(data_dir, trade_date))
    fresh = []
    already = []
    seen = set()
    for row in rows:
        key = (trade_date, row.code)
        if key in seen:
            continue
        seen.add(key)
        if key in present:
            already.append(row)
        else:
            fresh.append(row)
    if not fresh and not already:
        return 0
    written = upsert_prices(fresh + already, DailyPrice.SOURCE_BOARD)
    if fresh:
        append_rows(data_dir, trade_date, fresh)
    if already:
        update_session_rows(data_dir, trade_date, already)
    return written


def _isin_to_code() -> dict[str, str]:
    """Ticker for each ISIN. A symbol row wins over the seeded map."""
    found = dict(ISIN_TO_CODE)
    stored = Symbol.objects.exclude(isin__isnull=True).exclude(isin="").values_list("isin", "code")
    for isin, code in stored:
        found[isin] = code
    return found


def _save_unmapped(session_date: date, rows) -> None:
    """Remember sector-table names that still have no ticker. Prices stay unwritten."""
    for row in rows:
        PendingListing.objects.update_or_create(
            isin=row.isin,
            defaults={
                "name": row.name,
                "sector": row.sector,
                "session_date": session_date,
                "day_price": row.day_price,
                "volume": row.volume,
                "change_pct": row.change_pct,
            },
        )
    resolved = set(ISIN_TO_CODE)
    resolved.update(
        Symbol.objects.exclude(isin__isnull=True).exclude(isin="").values_list("isin", flat=True)
    )
    if resolved:
        PendingListing.objects.filter(isin__in=resolved).delete()


def _ensure_symbols(rows: list[PriceRow]) -> dict[str, Symbol]:
    latest: dict[str, tuple[date, str, str, str]] = {}
    for row in rows:
        current = latest.get(row.code)
        isin = (row.isin or "").strip().upper()
        sector = (row.sector or "").strip()
        if current is None or row.trade_date >= current[0]:
            latest[row.code] = (
                row.trade_date,
                row.name or row.code,
                isin or ("" if current is None else current[2]),
                sector or ("" if current is None else current[3]),
            )
        else:
            if isin and not current[2]:
                latest[row.code] = (current[0], current[1], isin, current[3])
            if sector and not latest[row.code][3]:
                kept = latest[row.code]
                latest[row.code] = (kept[0], kept[1], kept[2], sector)
    existing = {symbol.code: symbol for symbol in Symbol.objects.filter(code__in=latest)}
    created = []
    updated = []
    for code, (_, name, isin, sector) in latest.items():
        is_index = code.startswith("^")
        symbol = existing.get(code)
        if symbol is None:
            symbol = Symbol(
                code=code,
                name=name,
                is_index=is_index,
                isin=isin or None,
                sector=sector,
            )
            created.append(symbol)
            existing[code] = symbol
            continue
        fields = []
        if symbol.name != name:
            symbol.name = name
            fields.append("name")
        if symbol.is_index != is_index:
            symbol.is_index = is_index
            fields.append("is_index")
        if isin and symbol.isin != isin:
            symbol.isin = isin
            fields.append("isin")
        if sector and symbol.sector != sector:
            symbol.sector = sector
            fields.append("sector")
        if fields:
            updated.append(symbol)
    if created:
        Symbol.objects.bulk_create(created)
        existing = {symbol.code: symbol for symbol in Symbol.objects.filter(code__in=latest)}
    if updated:
        Symbol.objects.bulk_update(updated, ["name", "is_index", "isin", "sector"])
    return existing


def _finish(run: IngestRun, status: str, rows_written: int, error: str):
    run.status = status
    run.rows_written = rows_written
    run.error = error
    run.finished_at = timezone.now()
    run.save(update_fields=["status", "rows_written", "error", "finished_at"])
