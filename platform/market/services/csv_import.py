import csv
import os
from pathlib import Path

from django.conf import settings

from market.services.month_csv import existing_keys
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


def merge_missing_seed_rows() -> int:
    """Add seed rows whose date and code are not already in the mounted data files.

    Startup only copies a seed file when the destination is missing. A later
    correction in git would otherwise never reach the database.
    """
    seed_dir = Path(os.environ.get("SEED_DIR", "/app/seed-data"))
    if not seed_dir.is_dir():
        return 0
    data_dir = Path(settings.DATA_DIR)
    data_dir.mkdir(parents=True, exist_ok=True)
    added = 0
    for seed_path in sorted(seed_dir.glob("*.csv")):
        dest = data_dir / seed_path.name
        if not dest.exists() or dest.stat().st_size == 0:
            dest.write_bytes(seed_path.read_bytes())
            continue
        present = existing_keys(dest)
        extras = []
        for line in seed_path.read_text(encoding="utf-8-sig").splitlines()[1:]:
            if not line.strip():
                continue
            cells = next(csv.reader([line]))
            if len(cells) < 2:
                continue
            trade_date = parse_date(cells[0])
            code = cells[1].strip().upper()
            if trade_date is None or not code or (trade_date, code) in present:
                continue
            extras.append(line)
            present.add((trade_date, code))
        if not extras:
            continue
        tail = dest.read_bytes()[-1:]
        with dest.open("a", encoding="utf-8", newline="") as handle:
            if tail not in {b"\n", b"\r"}:
                handle.write("\n")
            handle.write("\n".join(extras) + "\n")
        added += len(extras)
    return added


def load_price_rows(data_dir: Path | None = None) -> list[PriceRow]:
    combined: dict[tuple, PriceRow] = {}
    for path in price_files(data_dir):
        for row in read_price_file(path):
            combined[(row.trade_date, row.code)] = row
    return list(combined.values())
