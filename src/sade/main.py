"""Sade web app."""

from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import config, extract, guard, mcp_takvim, otari, pipeline

ROOT = Path(__file__).resolve().parents[2]
STATIC = Path(__file__).parent / "static"
SAMPLES = ROOT / "samples"


@asynccontextmanager
async def lifespan(_: FastAPI):
    # The mounted MCP app's own lifespan does not run under FastAPI; start its
    # session manager here.
    async with mcp_takvim.server.session_manager.run():
        yield


app = FastAPI(title="Sade", lifespan=lifespan)


@app.middleware("http")
async def only_callbacks_through_tunnel(request: Request, call_next):
    """The app runs on localhost; a Cloudflare tunnel exposes it so Otari can
    call our MCP server and guardrail. Through the tunnel (requests carry
    cf-ray), serve only /x/<secret>/..., so nobody can spend our Otari
    budget via /api/analyze."""
    path = request.url.path
    prefix = f"/x/{config.PUBLIC_SECRET}/"
    via_tunnel = "cf-ray" in request.headers
    if path.startswith("/x/"):
        if not config.PUBLIC_SECRET or not secrets.compare_digest(path[: len(prefix)], prefix):
            return Response(status_code=404)
    elif via_tunnel:
        return Response(status_code=404)
    return await call_next(request)


app.include_router(guard.router)
app.mount("/static", StaticFiles(directory=STATIC), name="static")
if SAMPLES.exists():
    app.mount("/samples", StaticFiles(directory=SAMPLES), name="samples")


@app.get("/ics/{ics_id}.ics")
def ics(ics_id: str) -> Response:
    found = mcp_takvim.ics_bytes(ics_id)
    if not found:
        raise HTTPException(404)
    filename, data = found
    return Response(data, media_type="text/calendar",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/samples")
def samples() -> list[dict]:
    if not SAMPLES.exists():
        return []
    labels = {
        "vergi-ihbarnamesi": "Vergi / ceza ihbarnamesi",
        "icra-odeme-emri": "İcra ödeme emri",
        "kira-ihtarnamesi": "Kira ihtarnamesi",
        "e-devlet-trafik-cezasi": "e-Devlet trafik cezası",
        "vergi-ihbarnamesi-injection": "Vergi ihbarnamesi (gizli talimatlı)",
    }
    out = []
    for f in sorted(SAMPLES.iterdir()):
        if f.suffix.lower() in {".pdf", ".png", ".jpg"}:
            out.append({"file": f.name, "label": labels.get(f.stem, f.stem), "url": f"/samples/{f.name}"})
    return out


@app.post("/api/analyze")
async def analyze(
    file: UploadFile = File(...), simulate_outage: bool = Form(False), skip_masking: bool = Form(False),
):
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "Dosya 15 MB'tan büyük olamaz.")
    kind = extract.kind_of(file.filename or "", file.content_type)
    text = image_uri = None
    if kind == "pdf":
        text = extract.pdf_text(data)
        if not text:
            raise HTTPException(422, "PDF'de metin yok (taranmış olabilir). Sayfanın fotoğrafını yükleyin.")
    elif kind == "text":
        text = data.decode("utf-8", errors="replace")
    elif kind == "image":
        image_uri = extract.image_data_uri(data, max_side=1400, quality=80)
    else:
        raise HTTPException(415, "PDF, fotoğraf veya metin dosyası yükleyin.")

    try:
        return await pipeline.analyze(
            text=text, image_uri=image_uri, simulate_outage=simulate_outage, skip_masking=skip_masking,
        )
    except otari.OtariError as e:
        content = {
            "detail": f"Yapay zekâ servisi hata verdi: {e.status} {e.code or ''}".strip(),
            "otari": {"status": e.status, "code": e.code, "detail": e.detail},
            "calls": getattr(e, "calls", []),
            "guardrails": getattr(e, "guardrails", []),
        }
        if e.code == "guardrail_violation":
            reasons = [g.get("explanation") for g in (e.detail.get("guardrails") or []) if g.get("explanation")]
            content["detail"] = "Otari guardrail'i isteği durdurdu, belge modele gönderilmedi. " + " ".join(reasons)
        return JSONResponse(status_code=502 if e.status >= 500 else e.status, content=content)


# Otari-facing endpoints, under the secret prefix: MCP at /x/<secret>/mcp.
if config.PUBLIC_SECRET:
    app.mount(f"/x/{config.PUBLIC_SECRET}", mcp_takvim.app)


def run() -> None:
    import uvicorn

    uvicorn.run(
        "sade.main:app",
        host=os.getenv("SADE_HOST", "127.0.0.1"),
        port=int(os.getenv("SADE_PORT", "8000")),
        reload=os.getenv("SADE_RELOAD") == "1",
    )
