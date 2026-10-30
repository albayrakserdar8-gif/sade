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
#                      -> DeepSeek on DeepInfra -> Qwen3 235B (live fallback demo)
MODEL_ANALYST = os.getenv("SADE_MODEL_ANALYST", "sade-analyst")
MODEL_ANALYST_OUTAGE = os.getenv("SADE_MODEL_ANALYST_OUTAGE", "sade-analyst-demo")
MODEL_OCR = os.getenv("SADE_MODEL_OCR", "sade-ocr")
MODEL_CLASSIFIER = os.getenv("SADE_MODEL_CLASSIFIER", "mistralai/ministral-3-8b")
