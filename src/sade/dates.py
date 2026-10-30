"""Dates in Turkish letters: finding them, and legal-deadline arithmetic.

The holiday table is the single source used by the app, the MCP server and
the tests. Half days (arife) are working days in the morning; they are
listed separately and not treated as holidays.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

MONTHS = {
    "ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6,
    "temmuz": 7, "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12,
}
WEEKDAYS_TR = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]

# Official public holidays (full days). Religious holidays follow the
# Diyanet calendar; 2027 religious dates should be re-checked before use.
HOLIDAYS: dict[date, str] = {
    date(2026, 1, 1): "Yılbaşı",
    date(2026, 3, 20): "Ramazan Bayramı 1. gün",
    date(2026, 3, 21): "Ramazan Bayramı 2. gün",
    date(2026, 3, 22): "Ramazan Bayramı 3. gün",
    date(2026, 4, 23): "Ulusal Egemenlik ve Çocuk Bayramı",
    date(2026, 5, 1): "Emek ve Dayanışma Günü",
    date(2026, 5, 19): "Atatürk'ü Anma, Gençlik ve Spor Bayramı",
    date(2026, 5, 27): "Kurban Bayramı 1. gün",
    date(2026, 5, 28): "Kurban Bayramı 2. gün",
    date(2026, 5, 29): "Kurban Bayramı 3. gün",
    date(2026, 5, 30): "Kurban Bayramı 4. gün",
    date(2026, 7, 15): "Demokrasi ve Milli Birlik Günü",
    date(2026, 8, 30): "Zafer Bayramı",
    date(2026, 10, 29): "Cumhuriyet Bayramı",
    date(2027, 1, 1): "Yılbaşı",
    date(2027, 3, 9): "Ramazan Bayramı 1. gün",
    date(2027, 3, 10): "Ramazan Bayramı 2. gün",
    date(2027, 3, 11): "Ramazan Bayramı 3. gün",
    date(2027, 4, 23): "Ulusal Egemenlik ve Çocuk Bayramı",
    date(2027, 5, 1): "Emek ve Dayanışma Günü",
    date(2027, 5, 16): "Kurban Bayramı 1. gün",
    date(2027, 5, 17): "Kurban Bayramı 2. gün",
    date(2027, 5, 18): "Kurban Bayramı 3. gün",
    date(2027, 5, 19): "Kurban Bayramı 4. gün / Gençlik ve Spor Bayramı",
    date(2027, 7, 15): "Demokrasi ve Milli Birlik Günü",
    date(2027, 8, 30): "Zafer Bayramı",
    date(2027, 10, 29): "Cumhuriyet Bayramı",
}
HALF_DAYS: dict[date, str] = {
    date(2026, 3, 19): "Ramazan Bayramı arifesi (yarım gün)",
    date(2026, 5, 26): "Kurban Bayramı arifesi (yarım gün)",
    date(2026, 10, 28): "Cumhuriyet Bayramı arifesi (yarım gün)",
    date(2027, 3, 8): "Ramazan Bayramı arifesi (yarım gün)",
    date(2027, 5, 15): "Kurban Bayramı arifesi (yarım gün)",
    date(2027, 10, 28): "Cumhuriyet Bayramı arifesi (yarım gün)",
}


def holidays_in(year: int) -> list[tuple[date, str]]:
    return sorted((d, n) for d, n in HOLIDAYS.items() if d.year == year)


def is_business_day(d: date) -> bool:
    return d.weekday() < 5 and d not in HOLIDAYS


def next_business_day(d: date) -> date:
    while not is_business_day(d):
        d += timedelta(days=1)
    return d


def deadline(start: date, days: int) -> dict:
    """Count `days` calendar days from `start` (the day of service is not
    counted); if the last day is a weekend or holiday, move to the next
    business day (HMK 93, TBK 93, VUK 18)."""
    raw = start + timedelta(days=days)
    final = next_business_day(raw)
    return {
        "start": start.isoformat(),
        "days": days,
        "raw_end": raw.isoformat(),
        "raw_end_weekday": WEEKDAYS_TR[raw.weekday()],
        "deadline": final.isoformat(),
        "deadline_weekday": WEEKDAYS_TR[final.weekday()],
        "shifted": final != raw,
        "reason": None if final == raw else (HOLIDAYS.get(raw) or WEEKDAYS_TR[raw.weekday()]),
    }


def e_tebligat_service_date(delivered: date) -> date:
    """Electronic notification counts as served at the end of the fifth day
    after it reaches the e-box (Tebligat Kanunu 7/a)."""
    return delivered + timedelta(days=5)


_NUMERIC = re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b")
_WORDY = re.compile(r"\b(\d{1,2})\s+(" + "|".join(MONTHS) + r")\s+(\d{4})\b", re.IGNORECASE)


def find_dates(text: str) -> list[dict]:
    """Find dates and the words just before them (for context)."""
    out = []
    for m in _NUMERIC.finditer(text):
        day, month, year = map(int, m.groups())
        _append(out, text, m, day, month, year)
    for m in _WORDY.finditer(text):
        month = MONTHS[m.group(2).lower().replace("i̇", "i")]
        _append(out, text, m, int(m.group(1)), month, int(m.group(3)))
    out.sort(key=lambda x: x["pos"])
    return out


def _append(out, text, m, day, month, year):
    try:
        d = date(year, month, day)
    except ValueError:
        return
    line_start = text.rfind("\n", 0, m.start()) + 1
    out.append({
        "date": d.isoformat(),
        "text": m.group(0),
        "context": text[line_start:m.start()].strip()[-60:],
        "pos": m.start(),
    })
