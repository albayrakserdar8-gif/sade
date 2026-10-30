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

from . import config, dates, mcp_takvim, otari, privacy, prompts


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


async def analyze(
    *, text: str | None = None, image_uri: str | None = None, run_id: str | None = None,
    simulate_outage: bool = False,
) -> dict:
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

        today = date.today()
        holidays = ", ".join(
            f"{d.isoformat()} ({name})"
            for year in (today.year, today.year + 1)
            for d, name in dates.holidays_in(year) if d >= today
        )
        callback = config.callback_base()
        mcp_servers = []
        if callback:
            # Our own MCP server, reached by Otari through the tunnel. The run id
            # in the URL lets us show this run's MCP calls in the UI.
            mcp_servers.append({
                "name": "sade-takvim",
                "url": f"{callback}/mcp?run={run_id}",
                "purpose_hint": "Türkiye resmi tatilleri, iş günü kontrolü ve son tarihler için takvim etkinliği (.ics) oluşturma.",
                "allowed_tools": mcp_takvim.TOOL_NAMES,
            })
            holidays = "sade-takvim aracındaki resmi_tatiller ile al (gerekli her yıl için)."
        instructions = prompts.ANALYST.format(today=today.isoformat(), holidays=holidays)
        if mcp_servers:
            instructions += prompts.ANALYST_MCP
        hint = prompts.TYPE_HINTS.get(doc_class["doc_type"])
        if hint:
            label = prompts.DOC_TYPES[doc_class["doc_type"]]
            instructions += f"\nBelge türü ön sınıflandırması: {label}. Hatırlatma: {hint}\n"

        data, call = await otari.responses(
            role="analyze",
            model=config.MODEL_ANALYST_OUTAGE if simulate_outage else config.MODEL_ANALYST,
            instructions=instructions,
            input=prompts.analyst_input(masked.text),
            text_format=prompts.CARD_SCHEMA,
            tools=[
                # Otari runs the model's Python in its own sandbox, for any model.
                {"type": "code_interpreter"},
                # Otari's own web search and page fetch, to check the legal basis.
                {"type": "otari_web_search", "max_uses": 2},
                {"type": "otari_web_fetch"},
            ],
            headers={"Otari-Code-Execution": "otari"},
            # Every tool call is billed, so keep the tool loop short.
            extra={"max_tool_iterations": 7, **({"mcp_servers": mcp_servers} if mcp_servers else {})},
            conversation_id=run_id,
            metadata={"doc_type": doc_class["doc_type"]},
        )
        calls.append(call)
        card = otari.output_json(data)
        card["service_date"] = dates.to_iso(card.get("service_date"))
        for action in card.get("actions", []):
            action["deadline"] = dates.to_iso(action.get("deadline"))
    except otari.OtariError as e:
        if e.call:
            calls.append(e.call)
        e.calls = [c.to_dict() for c in calls]  # type: ignore[attr-defined]
        raise

    mcp_calls = mcp_takvim.CALL_LOG.pop(run_id, [])
    calendar = []
    for c in mcp_calls:
        if c["tool"] == "takvim_etkinligi_olustur" and isinstance(c["result"], dict):
            ics_id = c["result"]["ics_id"]
            mcp_takvim.personalize(ics_id, lambda t: privacy.unmask(t, masked.mapping))
            calendar.append({
                "title": privacy.unmask(c["result"]["baslik"], masked.mapping),
                "date": c["result"]["tarih"],
                "url": f"/ics/{ics_id}.ics",
            })

    return {
        "run_id": run_id,
        "source": "image" if image_uri else "text",
        "masked_text": masked.text,
        "pii": masked.counts,
        "dates": [{k: v for k, v in d.items() if k != "pos"} for d in dates.find_dates(masked.text)],
        "doc_class": doc_class,
        # The model only ever saw placeholders; put the person's own data back
        # for display, here on their side.
        "card": privacy.unmask_deep(card, masked.mapping),
        "calls": [c.to_dict() for c in calls],
        "mcp": {"connected": bool(mcp_servers), "calls": mcp_calls},
        "calendar": calendar,
        "cost_usd": round(sum(c.cost_usd for c in calls), 6),
    }
