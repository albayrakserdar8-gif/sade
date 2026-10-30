"""The analysis pipeline: a letter in, a plain-language card out.

Each step uses an open-weight model chosen for its role, all through Otari:
  ocr      photo -> text                  (vision model)
  classify text  -> document type         (small, fast model)
  analyze  text  -> card                  (strong model, with tools)
Every call is tagged with its role and the run id, so one analysis shows up
as one session on the Otari dashboard.
"""

from __future__ import annotations

import uuid
from datetime import date

from . import config, dates, otari, privacy, prompts


def new_run_id() -> str:
    return f"sade-{uuid.uuid4().hex[:12]}"


async def ocr(image_uri: str, *, run_id: str) -> tuple[str, otari.Call]:
    return await otari.chat(
        role="ocr",
        model=config.MODEL_OCR,
        max_tokens=2500,
        conversation_id=run_id,
        messages=[
            {"role": "system", "content": prompts.OCR},
            {"role": "user", "content": [
                {"type": "text", "text": "Belgenin metnini çıkar."},
                {"type": "image_url", "image_url": {"url": image_uri}},
            ]},
        ],
    )


async def classify(masked_text: str, *, run_id: str) -> tuple[dict, otari.Call]:
    text, call = await otari.chat(
        role="classify",
        model=config.MODEL_CLASSIFIER,
        max_tokens=200,
        conversation_id=run_id,
        response_format=prompts.CLASSIFY_SCHEMA,
        messages=[
            {"role": "system", "content": prompts.CLASSIFY},
            {"role": "user", "content": masked_text[:6000]},
        ],
    )
    result = otari.parse_json(text)
    if result.get("doc_type") not in prompts.DOC_TYPES:
        result["doc_type"] = "diger"
    return result, call


async def analyze(*, text: str | None = None, image_uri: str | None = None, run_id: str | None = None) -> dict:
    run_id = run_id or new_run_id()
    calls: list[otari.Call] = []
    try:
        if image_uri:
            text, call = await ocr(image_uri, run_id=run_id)
            calls.append(call)
        assert text is not None

        masked = privacy.mask(text)

        doc_class, call = await classify(masked.text, run_id=run_id)
        calls.append(call)

        instructions = prompts.ANALYST.format(today=date.today().isoformat())
        hint = prompts.TYPE_HINTS.get(doc_class["doc_type"])
        if hint:
            instructions += f"\nBelge türü ön sınıflandırması: {doc_class['doc_type']}. Hatırlatma: {hint}\n"

        data, call = await otari.responses(
            role="analyze",
            model=config.MODEL_ANALYST,
            instructions=instructions,
            input=prompts.analyst_input(masked.text),
            text_format=prompts.CARD_SCHEMA,
            conversation_id=run_id,
            metadata={"doc_type": doc_class["doc_type"]},
        )
        calls.append(call)
        card = otari.output_json(data)
    except otari.OtariError as e:
        if e.call:
            calls.append(e.call)
        e.calls = [c.to_dict() for c in calls]  # type: ignore[attr-defined]
        raise

    return {
        "run_id": run_id,
        "source": "image" if image_uri else "text",
        "masked_text": masked.text,
        "pii": masked.counts,
        "dates": [{k: v for k, v in d.items() if k != "pos"} for d in dates.find_dates(masked.text)],
        "doc_class": doc_class,
        "card": card,
        "calls": [c.to_dict() for c in calls],
        "cost_usd": round(sum(c.cost_usd for c in calls), 6),
    }
