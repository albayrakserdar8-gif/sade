"""Sade web app."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
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
async def analyze(file: UploadFile = File(...)) -> dict:
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "Dosya 15 MB'tan büyük olamaz.")
    kind = extract.kind_of(file.filename or "", file.content_type)
    if kind == "pdf":
        text = extract.pdf_text(data)
    elif kind == "text":
        text = data.decode("utf-8", errors="replace")
    elif kind == "image":
        raise HTTPException(501, "Fotoğraftan metin okuma (OCR) henüz bağlı değil.")
    else:
        raise HTTPException(415, "PDF, fotoğraf veya metin dosyası yükleyin.")
    if not text:
        raise HTTPException(422, "Belgeden metin çıkarılamadı.")

    try:
        return await pipeline.analyze_text(text)
    except otari.OtariError as e:
        raise HTTPException(502, f"Yapay zekâ servisi hata verdi: {e.status} {e.code or ''}") from e


def run() -> None:
    import uvicorn

    uvicorn.run(
        "sade.main:app",
        host=os.getenv("SADE_HOST", "127.0.0.1"),
        port=int(os.getenv("SADE_PORT", "8000")),
        reload=os.getenv("SADE_RELOAD") == "1",
    )
