import re
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

import requests
from pypdf import PdfReader

from market.services.afx import (
    NAIROBI,
    USER_AGENT,
    BoardParseError,
    SessionNotClosed,
    UnmappedQuote,
    _company_name,
)
from market.services.rows import PriceRow, parse_num, parse_volume

STATS_PAGE = "https://www.nse.co.ke/market-statistics/"
LIST_URL = "https://www.nse.co.ke/wp-content/uploads/{name}"
ISIN_RE = re.compile(r"\b((?:KE|UG)\d{10}|ZAE\d{9})\b")
DATE_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+(\d{1,2}),\s+(\d{4})",
    re.I,
)
SECTION_KEYS = (
    ("INVESTMENT SERVICES", "investse"),
    ("EXCHANGE TRADED", "exchange"),
    ("REAL ESTATE", "real"),
    ("TELECOMMUNICATION", "tele"),
    ("MANUFACTURING", "manu"),
    ("CONSTRUCTION", "const"),
    ("COMMERCIAL", "comm"),
    ("AGRICULTURAL", "agric"),
    ("AUTOMOBILES", "auto"),
    ("INSURANCE", "insr"),
    ("INVESTMENT", "invest"),
    ("BANKING", "bank"),
    ("ENERGY", "energy"),
)
STOP_MARKERS = ("CORPORATE ACTIONS", "ALL SHARE INDEX", "SECURITIES LENDING")


def fetch_equity_list(code_for_isin=None):
    """Latest closes from the NSE daily equity price list.

    That PDF is the published list. It includes new listings that the
    website sector tables still leave out.
    """
    data, named_date = _download_list()
    session_date, quotes, unmapped = parse_equity_pdf(data, code_for_isin, named_date)
    now = datetime.now(NAIROBI)
    if session_date == now.date() and (now.hour, now.minute) < (15, 30):
        raise SessionNotClosed(f"Nairobi time is {now:%H:%M}, before the 15:30 close.")
    return session_date, quotes, unmapped


def parse_equity_pdf(data: bytes, code_for_isin=None, named_date: date | None = None):
    resolve = code_for_isin or (lambda isin: None)
    images = _page_images(data)
    if not images:
        raise BoardParseError("The daily price list has no pages.")
    pages = [_ocr_words(image) for image in images]
    session_date = _session_date(pages) or named_date
    if session_date is None:
        raise BoardParseError("The daily price list has no session date.")
    quotes = []
    unmapped = []
    seen = set()
    seen_unmapped = set()
    for words in pages:
        if _page_stopped(words):
            continue
        headers = _headers(words)
        for isin_word in _isin_words(words):
            sector = _sector_above(isin_word[1], headers)
            row = _price_row(isin_word, words, session_date, sector, resolve)
            if row is None:
                continue
            if isinstance(row, UnmappedQuote):
                if row.isin in seen_unmapped:
                    continue
                seen_unmapped.add(row.isin)
                unmapped.append(row)
                continue
            if row.code in seen:
                continue
            seen.add(row.code)
            quotes.append(row)
    if not quotes and not unmapped:
        raise BoardParseError("The daily price list did not contain any prices.")
    return session_date, quotes, unmapped


def _download_list() -> tuple[bytes, date]:
    today = datetime.now(NAIROBI).date()
    name = f"{today.day:02d}-{_MONTHS_ABBR[today.month]}-{today.strftime('%y')}.pdf"
    response = requests.get(LIST_URL.format(name=name), headers={"User-Agent": USER_AGENT}, timeout=60)
    if response.status_code == 404:
        page = requests.get(STATS_PAGE, headers={"User-Agent": USER_AGENT}, timeout=60)
        page.raise_for_status()
        found = re.search(
            r'href="(https://www\.nse\.co\.ke/wp-content/uploads/(\d{2}-[A-Z]{3}-\d{2})\.pdf)"[^>]*>\s*Download Daily Equity Price List',
            page.text,
        )
        if found is None:
            raise BoardParseError("The NSE statistics page has no daily equity price list.")
        name = f"{found.group(2)}.pdf"
        response = requests.get(found.group(1), headers={"User-Agent": USER_AGENT}, timeout=60)
    response.raise_for_status()
    if not response.content.startswith(b"%PDF"):
        raise BoardParseError("The daily price list was not a PDF.")
    return response.content, _date_from_name(name)


_MONTHS_ABBR = (
    "",
    "JAN",
    "FEB",
    "MAR",
    "APR",
    "MAY",
    "JUN",
    "JUL",
    "AUG",
    "SEP",
    "OCT",
    "NOV",
    "DEC",
)


def _date_from_name(name: str) -> date:
    match = re.search(r"(\d{2})-([A-Z]{3})-(\d{2})", name.upper())
    if match is None:
        raise BoardParseError("The daily price list file name has no date.")
    month = _MONTHS_ABBR.index(match.group(2))
    return date(2000 + int(match.group(3)), month, int(match.group(1)))


def _page_images(data: bytes):
    reader = PdfReader(BytesIO(data))
    images = []
    for page in reader.pages:
        resources = page["/Resources"].get_object()
        xobjects = resources.get("/XObject")
        if xobjects is None:
            continue
        for ref in xobjects.get_object().values():
            obj = ref.get_object()
            if obj.get("/Subtype") != "/Image":
                continue
            width = int(obj["/Width"])
            height = int(obj["/Height"])
            raw = obj.get_data()
            if len(raw) != width * height * 3:
                raise BoardParseError("The daily price list image could not be read.")
            from PIL import Image

            images.append(Image.frombytes("RGB", (width, height), raw))
    return images


def _ocr_words(image):
    import numpy as np
    from rapidocr_onnxruntime import RapidOCR

    engine = _engine()
    result, _elapsed = engine(np.array(image))
    words = []
    for box, text, _score in result or []:
        cleaned = " ".join(str(text).split())
        if not cleaned:
            continue
        x = sum(point[0] for point in box) / 4
        y = sum(point[1] for point in box) / 4
        words.append((x, y, cleaned))
    return words


def _engine():
    engine = getattr(_engine, "cached", None)
    if engine is None:
        from rapidocr_onnxruntime import RapidOCR

        engine = RapidOCR()
        _engine.cached = engine
    return engine


def _session_date(pages):
    for words in pages:
        top = [text for _x, y, text in words if y < 500]
        match = DATE_RE.search(" ".join(top))
        if match:
            return datetime.strptime(match.group(0), "%B %d, %Y").date()
    return None


def _page_stopped(words) -> bool:
    text = " ".join(token for _x, _y, token in words).upper()
    return any(marker in text for marker in STOP_MARKERS) and not any(
        ISIN_RE.fullmatch(token.replace(" ", "")) for _x, _y, token in words
    )


def _headers(words):
    found = []
    for _x, y, text in words:
        key = _section_key(text)
        if key:
            found.append((y, key))
    return sorted(found)


def _sector_above(y, headers) -> str:
    sector = ""
    for header_y, key in headers:
        if header_y <= y + 8:
            sector = key
    return sector


def _isin_words(words):
    found = []
    for x, y, text in words:
        compact = text.replace(" ", "")
        if ISIN_RE.fullmatch(compact):
            found.append((x, y, compact))
    return sorted(found, key=lambda item: item[1])


def _section_key(text: str) -> str:
    compact = " ".join(text.upper().split())
    if ISIN_RE.search(compact) or any(char.isdigit() for char in compact):
        return ""
    if len(compact) > 40:
        return ""
    for label, key in SECTION_KEYS:
        if label in compact:
            return key
    return ""


def _price_row(isin_word, words, session_date: date, sector: str, resolve):
    isin_x, isin_y, isin = isin_word
    name_parts = []
    right = []
    for x, y, text in words:
        if abs(y - isin_y) > 12:
            continue
        if ";" in text or "announced" in text.lower():
            continue
        if x < isin_x and any(char.isalpha() for char in text):
            name_parts.append((x, text))
            continue
        if x <= isin_x:
            continue
        token = text.replace(",", "")
        if re.fullmatch(r"[A-Za-z]{1,3}", token) or parse_num(token) is None:
            continue
        right.append((x, token))
    numbers = []
    volume = None
    for _x, token in sorted(right):
        if "." not in token:
            volume = parse_volume(token)
            continue
        numbers.append(parse_num(token))
    name = _company_name(" ".join(text for _x, text in sorted(name_parts)))
    if len(numbers) >= 4:
        day_high, day_low, price, previous = numbers[:4]
    elif len(numbers) == 3:
        day_high, day_low, price = numbers
        previous = None
    elif len(numbers) == 1:
        day_high = day_low = None
        price = numbers[0]
        previous = None
    else:
        return None
    if price is None or price <= 0:
        return None
    change = None
    change_pct = None
    if previous not in (None, Decimal("0")):
        change = price - previous
        change_pct = (change / previous) * Decimal("100")
    code = resolve(isin)
    if not code:
        return UnmappedQuote(
            isin=isin,
            name=name or isin,
            sector=sector,
            day_price=price,
            volume=volume,
            change_pct=change_pct,
        )
    return PriceRow(
        trade_date=session_date,
        code=code,
        name=name or code,
        day_price=price,
        previous=previous,
        change=change,
        change_pct=change_pct,
        volume=volume,
        day_low=day_low,
        day_high=day_high,
        price_text=format(price, "f"),
        previous_text="" if previous is None else format(previous, "f"),
        change_pct_text="" if change_pct is None else f"{change_pct:.2f}%",
        volume_text="" if volume is None else str(volume),
        isin=isin,
        sector=sector,
    )
