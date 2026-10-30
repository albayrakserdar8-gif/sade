"""Get text out of an uploaded letter."""

from __future__ import annotations

import base64
import io

from PIL import Image
from pypdf import PdfReader

IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/heic"}


def kind_of(filename: str, content_type: str | None) -> str:
    name = filename.lower()
    if name.endswith(".pdf") or content_type == "application/pdf":
        return "pdf"
    if (content_type or "") in IMAGE_TYPES or name.endswith((".png", ".jpg", ".jpeg", ".webp")):
        return "image"
    if name.endswith(".txt") or (content_type or "").startswith("text/"):
        return "text"
    return "unknown"


def pdf_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def image_data_uri(data: bytes, max_side: int = 1800, quality: int = 85) -> str:
    """Downscale and re-encode an image as a JPEG data URI for a vision model."""
    img = Image.open(io.BytesIO(data))
    img = img.convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
