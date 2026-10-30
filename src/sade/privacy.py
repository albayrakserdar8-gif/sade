"""Find and mask personal data in Turkish official letters.

Masking happens before any text leaves this process. The mapping from
placeholder back to the original value stays in memory, so a draft written
with placeholders can be filled in locally.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


def is_valid_tckn(value: str) -> bool:
    """Check a Turkish national ID number (T.C. Kimlik No) checksum."""
    if len(value) != 11 or not value.isdigit() or value[0] == "0":
        return False
    d = [int(c) for c in value]
    d10 = ((d[0] + d[2] + d[4] + d[6] + d[8]) * 7 - (d[1] + d[3] + d[5] + d[7])) % 10
    d11 = sum(d[:10]) % 10
    return d[9] == d10 and d[10] == d11


def is_valid_iban(value: str) -> bool:
    """ISO 13616 mod-97 check."""
    iban = re.sub(r"\s", "", value).upper()
    if len(iban) < 15 or not iban[:2].isalpha():
        return False
    rearranged = iban[4:] + iban[:4]
    digits = "".join(str(int(c, 36)) for c in rearranged)
    return int(digits) % 97 == 1


# Labels whose value (until end of line) is a person's name or address.
_NAME_LABELS = r"(?:Ad[ıi] Soyad[ıi]|Ad[ıi] ve Soyad[ıi]|Ad Soyad|Mükellef(?:in)? Ad[ıi] Soyad[ıi]|Borçlu|Muhatap|Kirac[ıi]|Sürücü|Keşideci(?: \(İhtar Eden\))?)"
_ADDRESS_LABELS = r"(?:Adres(?:i)?|Tebliğ Adresi|İkametgah(?: Adresi)?)"

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("IBAN", re.compile(r"\bTR\d{2}(?:\s?\d{4}){5}\s?\d{2}\b", re.IGNORECASE)),
    ("TCKN", re.compile(r"(?<!\d)[1-9]\d{10}(?!\d)")),
    ("EPOSTA", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("TELEFON", re.compile(r"(?<!\d)(?:\+90\s?|0)\(?[2-5]\d{2}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d)")),
    ("PLAKA", re.compile(r"\b(?:0[1-9]|[1-7]\d|8[01])\s?[A-ZÇĞİÖŞÜ]{1,3}\s?\d{2,4}\b")),
]

_LABELLED: list[tuple[str, re.Pattern[str]]] = [
    ("AD", re.compile(rf"(?P<label>\b{_NAME_LABELS}\s*:\s*)(?P<value>[^\n(]+)")),
    ("ADRES", re.compile(rf"(?P<label>\b{_ADDRESS_LABELS}\s*:\s*)(?P<value>[^\n]+)")),
]

_VALIDATORS = {"TCKN": is_valid_tckn, "IBAN": is_valid_iban}


@dataclass
class MaskResult:
    text: str
    mapping: dict[str, str] = field(default_factory=dict)

    @property
    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for key in self.mapping:
            kind = key.strip("[]").rsplit("_", 1)[0]
            out[kind] = out.get(kind, 0) + 1
        return out


def find_pii(text: str) -> list[tuple[str, str]]:
    """Return (kind, value) pairs for every piece of personal data in text."""
    found: list[tuple[str, str]] = []
    for kind, pattern in _LABELLED:
        for m in pattern.finditer(text):
            value = m.group("value").strip(" .,;")
            if value and not value.startswith("["):
                found.append((kind, value))
    for kind, pattern in _PATTERNS:
        for m in pattern.finditer(text):
            value = m.group(0)
            check = _VALIDATORS.get(kind)
            if check and not check(value):
                continue
            found.append((kind, value))
    return found


def mask(text: str) -> MaskResult:
    """Replace personal data with numbered placeholders such as [TCKN_1]."""
    result = MaskResult(text=text)
    by_value: dict[str, str] = {}
    counters: dict[str, int] = {}
    # Longest values first, so a name inside an address line is not split.
    for kind, value in sorted(find_pii(text), key=lambda kv: -len(kv[1])):
        if value in by_value:
            continue
        counters[kind] = counters.get(kind, 0) + 1
        placeholder = f"[{kind}_{counters[kind]}]"
        by_value[value] = placeholder
        result.mapping[placeholder] = value
        result.text = result.text.replace(value, placeholder)
    return result


def unmask(text: str, mapping: dict[str, str]) -> str:
    for placeholder, value in mapping.items():
        text = text.replace(placeholder, value)
    return text


def unmask_deep(value, mapping: dict[str, str]):
    """unmask() every string inside nested dicts and lists."""
    if isinstance(value, str):
        return unmask(value, mapping)
    if isinstance(value, list):
        return [unmask_deep(v, mapping) for v in value]
    if isinstance(value, dict):
        return {k: unmask_deep(v, mapping) for k, v in value.items()}
    return value
