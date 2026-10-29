from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def parse_num(value):
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("%", "")
    if text in {"", "-", "nan", "None", "none"}:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def parse_volume(value):
    number = parse_num(value)
    if number is None:
        return None
    return int(number)


def parse_date(value):
    text = (value or "").strip()
    if not text:
        return None
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            pass
    parts = text.replace("/", "-").split("-")
    if len(parts) != 3:
        return None
    day_text, month_text, year_text = parts
    if month_text.isdigit():
        day_text, month_text = month_text, day_text
        try:
            day = int(day_text)
            month = int(month_text)
            year = int(year_text)
        except ValueError:
            return None
    else:
        month = MONTHS.get(month_text[:3].lower())
        if month is None:
            return None
        try:
            day = int(day_text)
            year = int(year_text)
        except ValueError:
            return None
    if year < 100:
        year += 2000
    try:
        return date(year, month, day)
    except ValueError:
        return None


def format_csv_date(value: date) -> str:
    return f"{value.day}-{value.strftime('%b')}-{value.strftime('%y')}"


def format_decimal(value: Decimal | None) -> str:
    if value is None:
        return ""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def format_change_pct(value: Decimal | None) -> str:
    if value is None:
        return ""
    return f"{value:.2f}%"


def month_file_sort_key(path_name: str) -> datetime:
    stem = path_name[:-4] if path_name.lower().endswith(".csv") else path_name
    parts = stem.split("_")
    if len(parts) >= 3 and parts[2].isdigit():
        month = MONTHS.get(parts[1][:3].lower())
        if month:
            return datetime(int(parts[2]), month, 1)
    return datetime.min


@dataclass
class PriceRow:
    trade_date: date
    code: str
    name: str
    day_price: Decimal
    previous: Decimal | None = None
    change: Decimal | None = None
    change_pct: Decimal | None = None
    volume: int | None = None
    day_low: Decimal | None = None
    day_high: Decimal | None = None
    price_text: str = ""
    previous_text: str = ""
    change_text: str = ""
    change_pct_text: str = ""
    volume_text: str = ""
