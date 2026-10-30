"""Settings, read from the environment (and .env)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

OTARI_API_BASE = os.getenv("OTARI_API_BASE", "https://otari.ai").rstrip("/")
OTARI_API_KEY = os.getenv("OTARI_API_KEY", "")

# Every model is open-weight and reached through Otari. The analyst and OCR
# roles call Otari routing policies (created in the dashboard) instead of a
# model, so Otari picks the model and falls back when a provider fails:
#   sade-analyst       DeepSeek V4.1 Flash 1017 -> Qwen3 235B Instruct 2507
#   sade-ocr           DeepSeek V4.1 Flash 1017 -> Qwen3 VL 235B
#   sade-analyst-demo  DeepSeek on a provider with a deliberately broken key
#                      -> DeepSeek on DeepInfra -> Qwen3 235B (live fallback demo,
#                      used for OCR and drafts when "simulate outage" is on)
MODEL_ANALYST = os.getenv("SADE_MODEL_ANALYST", "sade-analyst")
MODEL_ANALYST_OUTAGE = os.getenv("SADE_MODEL_ANALYST_OUTAGE", "sade-analyst-demo")
MODEL_OCR = os.getenv("SADE_MODEL_OCR", "sade-ocr")

# Policy-level fallbacks done by the app (see otari.py). Hosted Otari does not
# fall back to a policy's next candidate on streamed requests that declare
# gateway-run tools, so when such a request fails before any output, the app
# sends it to the next policy here. All of them are Otari routing policies:
#   sade-analyst-backup  DeepSeek V4.1 Flash 1017 on Fireworks -> on Nebius
#                        -> Qwen3 235B (different providers from sade-analyst)
POLICY_FALLBACKS: dict[str, list[str]] = {
    "sade-analyst-demo": ["sade-analyst"],
    "sade-analyst": ["sade-analyst-backup"],
}
if os.getenv("SADE_POLICY_FALLBACKS") == "off":
    POLICY_FALLBACKS = {}
MODEL_CLASSIFIER = os.getenv("SADE_MODEL_CLASSIFIER", "mistralai/ministral-3-8b")

# Otari calls back into this app (our MCP server and guardrail service)
# through a public tunnel. Those endpoints live under /x/<secret>/ and
# nothing else is served to the tunnel.
PUBLIC_SECRET = os.getenv("SADE_PUBLIC_SECRET", "")
_TUNNEL_FILE = ROOT / ".tunnel-url"


def public_url() -> str | None:
    """The tunnel's https URL: SADE_PUBLIC_URL, or the file scripts/tunnel.sh writes."""
    url = os.getenv("SADE_PUBLIC_URL")
    if not url and _TUNNEL_FILE.exists():
        url = _TUNNEL_FILE.read_text().strip()
    return url.rstrip("/") if url and PUBLIC_SECRET else None


def callback_base() -> str | None:
    url = public_url()
    return f"{url}/x/{PUBLIC_SECRET}" if url else None

# Guardrail judge for prompt injection hidden in letters (open-weight policy classifier).
MODEL_GUARD = os.getenv("SADE_MODEL_GUARD", "openai/gpt-oss-safeguard-120b")
