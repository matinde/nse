import csv
from pathlib import Path

from django.conf import settings

from market.services.rows import PriceRow, month_file_sort_key, parse_date, parse_num, parse_volume


def price_files(data_dir: Path | None = None) -> list[Path]:
    root = Path(data_dir or settings.DATA_DIR)
    yearly = [root / name for name in settings.YEARLY_PRICE_FILES]
    missing = [path.name for path in yearly if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing price file(s): " + ", ".join(missing))
    monthly = sorted(root.glob("NSE_*_prices.csv"), key=lambda path: month_file_sort_key(path.name))
    return yearly + monthly


def read_price_file(path: Path) -> list[PriceRow]:
    rows = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            trade_date = parse_date(raw.get("Date"))
            code = (raw.get("Code") or "").strip().upper()
            price = parse_num(raw.get("Day Price"))
            if trade_date is None or not code or price is None:
                continue
            rows.append(
                PriceRow(
                    trade_date=trade_date,
                    code=code,
                    name=(raw.get("Name") or code).strip(),
                    day_price=price,
                    previous=parse_num(raw.get("Previous")),
                    change=parse_num(raw.get("Change")),
                    change_pct=parse_num(raw.get("Change%")),
                    volume=parse_volume(raw.get("Volume")),
                    day_low=parse_num(raw.get("Day Low")),
                    day_high=parse_num(raw.get("Day High")),
                )
            )
    return rows


def load_price_rows(data_dir: Path | None = None) -> list[PriceRow]:
    combined: dict[tuple, PriceRow] = {}
    for path in price_files(data_dir):
        for row in read_price_file(path):
            combined[(row.trade_date, row.code)] = row
    return list(combined.values())
