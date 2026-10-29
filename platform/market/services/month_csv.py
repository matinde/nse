import csv
from datetime import date
from pathlib import Path

from market.services.rows import (
    PriceRow,
    format_change_pct,
    format_csv_date,
    format_decimal,
    parse_date,
)

HEADER = [
    "Date",
    "Code",
    "Name",
    "12m Low",
    "12m High",
    "Day Low",
    "Day High",
    "Day Price",
    "Previous",
    "Change",
    "Change%",
    "Volume",
    "Adjusted Price",
]


def month_path(data_dir: Path, trade_date: date) -> Path:
    return data_dir / f"NSE_{trade_date.strftime('%B')}_{trade_date.year}_prices.csv"


def existing_keys(path: Path) -> set[tuple[date, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return set()
    keys = set()
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for raw in csv.DictReader(handle):
            trade_date = parse_date(raw.get("Date"))
            code = (raw.get("Code") or "").strip().upper()
            if trade_date is not None and code:
                keys.add((trade_date, code))
    return keys


def _cell(text: str, fallback) -> str:
    if text:
        return text
    rendered = fallback()
    return rendered


def append_rows(data_dir: Path, trade_date: date, rows: list[PriceRow]) -> int:
    path = month_path(data_dir, trade_date)
    present = existing_keys(path)
    fresh = [row for row in rows if (trade_date, row.code) not in present]
    if not fresh:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists() or path.stat().st_size == 0
    needs_break = False
    if not new_file:
        with path.open("rb") as handle:
            handle.seek(-1, 2)
            needs_break = handle.read(1) not in {b"\n", b"\r"}
    with path.open("a", newline="", encoding="utf-8") as handle:
        if needs_break:
            handle.write("\n")
        writer = csv.writer(handle)
        if new_file:
            writer.writerow(HEADER)
        for row in fresh:
            writer.writerow(
                [
                    format_csv_date(trade_date),
                    row.code,
                    row.name,
                    "",
                    "",
                    "",
                    "",
                    _cell(row.price_text, lambda row=row: format_decimal(row.day_price)),
                    _cell(row.previous_text, lambda row=row: format_decimal(row.previous)),
                    _cell(row.change_text, lambda row=row: format_decimal(row.change)),
                    _cell(row.change_pct_text, lambda row=row: format_change_pct(row.change_pct)),
                    _cell(row.volume_text, lambda row=row: "" if row.volume is None else str(row.volume)),
                    "-",
                ]
            )
    return len(fresh)
