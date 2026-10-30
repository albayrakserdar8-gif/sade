"""sade-takvim: our MCP server (streamable HTTP), called by Otari.

Otari connects to it during an analysis (inline `mcp_servers` in the
request) and lets the model use three tools: Turkish public holidays, a
working-day check, and creating a calendar event (.ics) for a deadline.

The URL Otari gets carries the analysis run id (?run=...), so every tool
call is logged per run and the UI can show what the model did over MCP
(Otari's Chat/Responses output does not report MCP calls).
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from . import dates

server = MCPServer(
    "sade-takvim",
    instructions="Türkiye resmi tatilleri, iş günü kontrolü ve son tarihler için takvim etkinliği (.ics).",
)

# run id -> tool calls, and ics id -> event fields. In memory: a demo app.
CALL_LOG: dict[str, list[dict]] = defaultdict(list)
ICS_FILES: dict[str, dict] = {}


def _run_id(ctx: Context | None) -> str:
    try:
        request = ctx.request_context.request  # the Starlette request (HTTP transport)
        return request.query_params.get("run") or "unknown"
    except Exception:
        return "unknown"


def _log(ctx: Context | None, tool: str, args: dict, result) -> None:
    CALL_LOG[_run_id(ctx)].append({"tool": tool, "args": args, "result": result, "at": time.time()})


def _parse(value: str) -> date:
    iso = dates.to_iso(value)
    if not iso:
        raise ValueError(f"Tarih anlaşılamadı: {value!r}. YYYY-AA-GG biçiminde verin.")
    return date.fromisoformat(iso)


@server.tool()
def resmi_tatiller(yil: int, ctx: Context) -> list[dict]:
    """Türkiye'de verilen yıldaki resmi tatil günleri (tam gün) ve yarım gün arifeler.
    Son tarih hesaplarında, son gün bunlardan birine denk gelirse sonraki iş gününe kayar."""
    result = [
        {"tarih": d.isoformat(), "ad": name, "gun": dates.WEEKDAYS_TR[d.weekday()], "tur": "tam gün"}
        for d, name in dates.holidays_in(yil)
    ] + [
        {"tarih": d.isoformat(), "ad": name, "gun": dates.WEEKDAYS_TR[d.weekday()], "tur": "yarım gün"}
        for d, name in sorted(dates.HALF_DAYS.items()) if d.year == yil
    ]
    _log(ctx, "resmi_tatiller", {"yil": yil}, f"{len(result)} gün")
    return result


@server.tool()
def is_gunu_mu(tarih: str, ctx: Context) -> dict:
    """Bir tarihin iş günü olup olmadığını ve değilse sonraki ilk iş gününü söyler. Tarih: YYYY-AA-GG."""
    d = _parse(tarih)
    nxt = dates.next_business_day(d)
    result = {
        "tarih": d.isoformat(),
        "gun": dates.WEEKDAYS_TR[d.weekday()],
        "is_gunu": dates.is_business_day(d),
        "neden": dates.HOLIDAYS.get(d) or ("hafta sonu" if d.weekday() >= 5 else None),
        "sonraki_is_gunu": nxt.isoformat(),
        "sonraki_is_gunu_gun": dates.WEEKDAYS_TR[nxt.weekday()],
    }
    _log(ctx, "is_gunu_mu", {"tarih": tarih}, result)
    return result


def _ics(title: str, day: date, description: str, remind_days: int) -> bytes:
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

    uid = f"{uuid.uuid4()}@sade"
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Sade//sade-takvim//TR", "CALSCALE:GREGORIAN",
        "BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp}",
        f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}",
        f"DTEND;VALUE=DATE:{(day + timedelta(days=1)).strftime('%Y%m%d')}",
        f"SUMMARY:{esc(title)}", f"DESCRIPTION:{esc(description)}",
        "BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{esc(title)}",
        f"TRIGGER:-P{max(remind_days, 0)}D", "END:VALARM",
        "END:VEVENT", "END:VCALENDAR",
    ]
    return ("\r\n".join(lines) + "\r\n").encode()


@server.tool()
def takvim_etkinligi_olustur(
    baslik: str, tarih: str, aciklama: str, ctx: Context, hatirlatma_gun_once: int = 2
) -> dict:
    """Bir son tarih için takvim etkinliği (.ics) oluşturur; kullanıcı tek tıkla kendi
    takvimine ekler. Her önemli son tarih için bir kez çağır. Tarih: YYYY-AA-GG."""
    d = _parse(tarih)
    ics_id = uuid.uuid4().hex[:12]
    filename = f"sade-{d.isoformat()}.ics"
    ICS_FILES[ics_id] = {
        "filename": filename, "title": baslik, "date": d, "description": aciklama, "remind": hatirlatma_gun_once,
    }
    result = {
        "olusturuldu": True,
        "baslik": baslik,
        "tarih": d.isoformat(),
        "gun": dates.WEEKDAYS_TR[d.weekday()],
        "is_gunu": dates.is_business_day(d),
        "ics_id": ics_id,
        "hatirlatma": f"{hatirlatma_gun_once} gün önce",
    }
    _log(ctx, "takvim_etkinligi_olustur", {"baslik": baslik, "tarih": tarih, "aciklama": aciklama}, result)
    return result


def ics_bytes(ics_id: str) -> tuple[str, bytes] | None:
    event = ICS_FILES.get(ics_id)
    if not event:
        return None
    return event["filename"], _ics(event["title"], event["date"], event["description"], event["remind"])


def personalize(ics_id: str, unmask) -> None:
    """The model wrote the event with placeholders ([IBAN_1]); fill in the
    person's real data here, locally, before they download it."""
    event = ICS_FILES.get(ics_id)
    if event:
        event["title"] = unmask(event["title"])
        event["description"] = unmask(event["description"])


TOOL_NAMES = ["resmi_tatiller", "is_gunu_mu", "takvim_etkinligi_olustur"]

# Otari reaches us through a public tunnel, so the Host header is the
# tunnel's. Access is limited by the secret path instead (see main.py).
app = server.streamable_http_app(
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)
