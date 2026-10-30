"""Demo users and their per-user budgets.

Hosted Otari does not let a tenant create service keys (the documented way
to bill many end users on one key), so each user gets their own Otari API
key, and each key holds its own budget, set in the Otari dashboard
(Spend & budgets -> a spend ceiling on that key). Otari enforces the
budget; when it runs out, requests on that key get 403 budget_exceeded.

Otari does not let an API key read its remaining budget, so the app keeps
its own running total from each response's usage.cost_usd, for display only.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import date

from . import config


@dataclass(frozen=True)
class Persona:
    id: str
    name: str
    key_env: str
    limit_usd: float
    period: str  # "monthly" | "daily"
    note: str

    @property
    def api_key(self) -> str | None:
        return os.getenv(self.key_env)


PERSONAS = [
    Persona("ayse", "Ayşe", "OTARI_KEY_AYSE", 1.00, "monthly", "Aylık 1 $"),
    Persona("zeynep", "Zeynep", "OTARI_KEY_ZEYNEP", 1.00, "monthly", "Aylık 1 $"),
    Persona("mehmet", "Mehmet", "OTARI_KEY_MEHMET", 0.05, "daily", "Günlük 0,05 $ (deneme hesabı)"),
]
BY_ID = {p.id: p for p in PERSONAS}

_USAGE_FILE = config.ROOT / "data" / "usage.json"
_lock = threading.Lock()


def _period_key(p: Persona, today: date | None = None) -> str:
    today = today or date.today()
    return today.isoformat() if p.period == "daily" else today.strftime("%Y-%m")


def _load() -> dict:
    try:
        return json.loads(_USAGE_FILE.read_text())
    except (FileNotFoundError, ValueError):
        return {}


def record(persona_id: str, cost_usd: float) -> None:
    p = BY_ID.get(persona_id)
    if not p or cost_usd <= 0:
        return
    with _lock:
        data = _load()
        key = f"{p.id}:{_period_key(p)}"
        data[key] = round(data.get(key, 0.0) + cost_usd, 6)
        _USAGE_FILE.parent.mkdir(exist_ok=True)
        _USAGE_FILE.write_text(json.dumps(data, indent=2))


def spent(persona_id: str) -> float:
    p = BY_ID[persona_id]
    return _load().get(f"{p.id}:{_period_key(p)}", 0.0)


def listing() -> list[dict]:
    return [
        {"id": p.id, "name": p.name, "note": p.note, "limit_usd": p.limit_usd, "period": p.period,
         "spent_usd": spent(p.id), "configured": bool(p.api_key)}
        for p in PERSONAS
    ]
