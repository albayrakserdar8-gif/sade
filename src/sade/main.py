"""Sade web app."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import extract, otari, pipeline

ROOT = Path(__file__).resolve().parents[2]
STATIC = Path(__file__).parent / "static"
SAMPLES = ROOT / "samples"

app = FastAPI(title="Sade")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
if SAMPLES.exists():
    app.mount("/samples", StaticFiles(directory=SAMPLES), name="samples")


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
async def analyze(file: UploadFile = File(...), simulate_outage: bool = Form(False)):
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
        return await pipeline.analyze(text=text, image_uri=image_uri, simulate_outage=simulate_outage)
    except otari.OtariError as e:
        return JSONResponse(
            status_code=502 if e.status >= 500 else e.status,
            content={"detail": f"Yapay zekâ servisi hata verdi: {e.status} {e.code or ''}".strip(),
                     "otari": {"status": e.status, "code": e.code, "detail": e.detail},
                     "calls": getattr(e, "calls", [])},
        )


def run() -> None:
    import uvicorn

    uvicorn.run(
        "sade.main:app",
        host=os.getenv("SADE_HOST", "127.0.0.1"),
        port=int(os.getenv("SADE_PORT", "8000")),
        reload=os.getenv("SADE_RELOAD") == "1",
    )
