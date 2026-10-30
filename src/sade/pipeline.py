"""The analysis pipeline: letter text in, plain-language card out."""

from __future__ import annotations

import uuid
from datetime import date

from . import config, dates, otari, privacy, prompts


async def analyze_text(text: str, *, run_id: str | None = None) -> dict:
    run_id = run_id or f"sade-{uuid.uuid4().hex[:12]}"
    calls: list[otari.Call] = []

    masked = privacy.mask(text)

    data, call = await otari.responses(
        role="analyze",
        model=config.MODEL_ANALYST,
        instructions=prompts.ANALYST.format(today=date.today().isoformat()),
        input=prompts.analyst_input(masked.text),
        text_format=prompts.CARD_SCHEMA,
        conversation_id=run_id,
    )
    calls.append(call)
    card = otari.output_json(data)

    return {
        "run_id": run_id,
        "masked_text": masked.text,
        "pii": masked.counts,
        "dates": [{k: v for k, v in d.items() if k != "pos"} for d in dates.find_dates(masked.text)],
        "card": card,
        "calls": [c.to_dict() for c in calls],
        "cost_usd": round(sum(c.cost_usd for c in calls), 6),
    }
