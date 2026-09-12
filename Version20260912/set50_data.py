"""SET50 index constituent list management.

Constituents are published by SET twice a year (H1: Jan-Jun, H2: Jul-Dec),
as official PDFs. This module:

- ships the two periods you provided (H1 2026, H2 2026) as a built-in
  default so the app works out of the box;
- can parse a new SET-format PDF (upload or scrape) and add it as another
  period;
- persists any uploaded/scraped periods locally so they survive restarts;
- picks the right constituent list for any given date.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

PERIODS_PATH = Path(__file__).parent / "set50_periods.json"

# Built into the app: the two official periods you supplied, parsed from
# SET's PDFs (SET50_100_H1_2026.pdf and SET50_SET100_H2_2026_revise.pdf).
BUILTIN_PERIODS = [
    {
        "start": "2026-01-01",
        "end": "2026-06-30",
        "source": "builtin (SET50_100_H1_2026.pdf)",
        "tickers": [
            "ADVANC", "AOT", "AWC", "BANPU", "BBL", "BDMS", "BEM", "BH", "BJC",
            "BTS", "CBG", "CCET", "CENTEL", "COM7", "CPALL", "CPF", "CPN",
            "CRC", "DELTA", "EGCO", "GPSC", "GULF", "HMPRO", "IVL", "KBANK",
            "KKP", "KTB", "KTC", "LH", "MINT", "MTC", "OR", "OSP", "PTT",
            "PTTEP", "PTTGC", "RATCH", "SAWAD", "SCB", "SCC", "SCGP", "TCAP",
            "TIDLOR", "TISCO", "TLI", "TOP", "TRUE", "TTB", "TU", "WHA",
        ],
    },
    {
        "start": "2026-07-01",
        "end": "2026-12-31",
        "source": "builtin (SET50_SET100_H2_2026_revise.pdf)",
        "tickers": [
            "ADVANC", "AOT", "AWC", "BANPU", "BBL", "BCP", "BDMS", "BEM",
            "BH", "BJC", "CCET", "COM7", "CPALL", "CPF", "CPN", "CRC",
            "DELTA", "EGCO", "GPSC", "GULF", "HMPRO", "IVL", "KBANK", "KKP",
            "KTB", "KTC", "LH", "MINT", "MRDIYT", "MTC", "OR", "OSP", "PTT",
            "PTTEP", "PTTGC", "RATCH", "SCB", "SCC", "SCGP", "TCAP", "TFG",
            "THAI", "TIDLOR", "TISCO", "TLI", "TOP", "TRUE", "TTB", "TU",
            "WHA",
        ],
    },
]

MONTH_TO_NUM = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}


def _parse_period_date(text: str, year_hint: int | None = None) -> dt.date | None:
    """Parse a date like 'January 1' or 'June 30, 2026' into a date."""
    m = re.match(r"([A-Za-z]+)\s+(\d{1,2})(?:,?\s*(\d{4}))?", text.strip())
    if not m:
        return None
    month_name, day, year = m.group(1).lower(), int(m.group(2)), m.group(3)
    month = MONTH_TO_NUM.get(month_name)
    if not month:
        return None
    year = int(year) if year else year_hint
    if year is None:
        return None
    return dt.date(year, month, day)


def parse_set50_pdf(pdf_path) -> dict:
    """Parse a SET-format SET50/SET100 constituents PDF.

    Extracts the SET50 section only (stops before the SET100 section) and
    the effective date range from the "For calculating the index during
    <start> - <end>" line.

    Raises ValueError if the expected structure isn't found.
    """
    import pdfplumber

    full_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            full_text += t + "\n"
            if "SET100 / SET100FF" in t:
                break

    m = re.search(r"For calculating the index during ([^\n]+)", full_text)
    if not m:
        raise ValueError("Could not find the 'For calculating the index during ...' line in this PDF.")
    period_text = m.group(1).strip()
    parts = [p.strip() for p in period_text.split(" - ")]
    if len(parts) != 2:
        raise ValueError(f"Could not parse the period range: '{period_text}'")
    end_date = _parse_period_date(parts[1])
    if end_date is None:
        raise ValueError(f"Could not parse the end date: '{parts[1]}'")
    start_date = _parse_period_date(parts[0], year_hint=end_date.year)
    if start_date is None:
        raise ValueError(f"Could not parse the start date: '{parts[0]}'")

    lines = full_text.split("\n")
    tickers: list[str] = []
    started = False
    for line in lines:
        line = line.strip()
        if re.match(r"^No\s+Symbol\s+Company Name\s+Sector", line):
            started = True
            continue
        if line.startswith("Inclusion") or "SET100" in line:
            break
        if started:
            mm = re.match(r"^(\d+)\s+([A-Z0-9]+)\s+(.*)$", line)
            if mm:
                tickers.append(mm.group(2))

    if len(tickers) < 40:
        raise ValueError(f"Only found {len(tickers)} tickers — this doesn't look like a valid SET50 PDF.")

    return {
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "source": f"uploaded PDF ({period_text})",
        "tickers": tickers,
    }


def load_custom_periods() -> list[dict]:
    if not PERIODS_PATH.exists():
        return []
    try:
        data = json.loads(PERIODS_PATH.read_text())
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def save_custom_periods(periods: list[dict]) -> None:
    PERIODS_PATH.write_text(json.dumps(periods, indent=2))


def add_period(new_period: dict) -> list[dict]:
    """Add (or replace, if the same start date exists) a custom period."""
    periods = load_custom_periods()
    periods = [p for p in periods if p["start"] != new_period["start"]]
    periods.append(new_period)
    periods.sort(key=lambda p: p["start"])
    save_custom_periods(periods)
    return periods


def all_periods() -> list[dict]:
    """Custom (scraped/uploaded) periods take priority over built-in ones
    when their start dates coincide; otherwise all periods are merged and
    sorted by start date."""
    custom = load_custom_periods()
    custom_starts = {p["start"] for p in custom}
    merged = [p for p in BUILTIN_PERIODS if p["start"] not in custom_starts] + custom
    merged.sort(key=lambda p: p["start"])
    return merged


def constituents_for_date(target_date: dt.date) -> tuple[list[str], dict | None]:
    """Return (tickers, period_dict) for the period covering `target_date`.

    If no period covers the date (e.g. it's beyond the last known period),
    fall back to the most recent period and return it with a note.
    """
    periods = all_periods()
    for p in periods:
        start = dt.date.fromisoformat(p["start"])
        end = dt.date.fromisoformat(p["end"])
        if start <= target_date <= end:
            return p["tickers"], p
    if periods:
        latest = max(periods, key=lambda p: p["start"])
        return latest["tickers"], latest
    return [], None


def try_scrape_latest_period() -> dict:
    """Best-effort: check SET's constituents page for a newer PDF, download
    and parse it. Raises on any failure (network, parsing, structure
    change) — callers should catch and fall back to PDF upload.
    """
    import io

    import requests
    from bs4 import BeautifulSoup

    listing_url = "https://www.set.or.th/en/market/information/securities-list/constituents-list-set50-set100"
    resp = requests.get(listing_url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    pdf_links = [
        a["href"] for a in soup.find_all("a", href=True)
        if re.search(r"SET50.*\.pdf$", a["href"], re.IGNORECASE)
    ]
    if not pdf_links:
        raise ValueError("No SET50 PDF links found on the constituents page — site structure may have changed.")

    # Prefer links that look like they're for the current or a future year.
    current_year = dt.date.today().year
    pdf_links.sort(key=lambda u: (str(current_year) not in u, u), reverse=False)
    pdf_url = pdf_links[0]
    if not pdf_url.startswith("http"):
        pdf_url = f"https://www.set.or.th{pdf_url}"

    pdf_resp = requests.get(pdf_url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    pdf_resp.raise_for_status()

    period = parse_set50_pdf(io.BytesIO(pdf_resp.content))
    period["source"] = f"scraped ({pdf_url})"
    return period
