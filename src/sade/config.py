"""Settings, read from the environment (and .env)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

OTARI_API_BASE = os.getenv("OTARI_API_BASE", "https://otari.ai").rstrip("/")
OTARI_API_KEY = os.getenv("OTARI_API_KEY", "")

# Every model is open-weight and reached through Otari.
MODEL_ANALYST = os.getenv("SADE_MODEL_ANALYST", "deepseek/deepseek-v4.1-flash-1017")
MODEL_OCR = os.getenv("SADE_MODEL_OCR", "deepseek/deepseek-v4.1-flash-1017")
MODEL_CLASSIFIER = os.getenv("SADE_MODEL_CLASSIFIER", "mistralai/ministral-3-8b")
