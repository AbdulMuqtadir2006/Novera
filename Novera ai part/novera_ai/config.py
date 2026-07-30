"""Central configuration for the NOVERA AI service."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "auto").strip() or "auto"
OPENROUTER_TIMEOUT = max(15, int(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "60")))

# `auto` -> OpenRouter's free auto-router; otherwise use the configured slug.
RESOLVED_MODEL = "openrouter/free" if OPENROUTER_MODEL.lower() == "auto" else OPENROUTER_MODEL

AI_ENABLED = bool(OPENROUTER_API_KEY.startswith("sk-or-"))

# WhatsApp — Meta (Facebook) Cloud API
META_WHATSAPP_TOKEN = os.getenv("META_WHATSAPP_TOKEN", "").strip()   # access token (temp 24h or system-user)
META_PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID", "").strip()  # numeric Phone Number ID (NOT the phone)
META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "").strip()        # you invent this; must match the dashboard
META_APP_SECRET = os.getenv("META_APP_SECRET", "").strip()           # optional: verifies X-Hub-Signature-256
META_API_VERSION = os.getenv("META_API_VERSION", "v22.0").strip() or "v22.0"
WHATSAPP_TO = os.getenv("WHATSAPP_TO", "").strip()  # default recipient in E.164, e.g. +9689...
WHATSAPP_ENABLED = bool(META_WHATSAPP_TOKEN and META_PHONE_NUMBER_ID)

# Clinic — Badr Al Sama, Al Khuwair (Muscat)
CLINIC_NAME = "Badr Al Samaa"
CLINIC_BRANCH = "Al Khuwair"
CLINIC_ADDRESS = "Badr Al Samaa Medical Centre, Al Khuwair, Muscat, Oman"
CLINIC_MAPS_URL = "https://maps.google.com/?q=Badr+Al+Samaa+Al+Khuwair+Muscat"
CLINIC_PHONE = "+968 2479 8800"

# Doctor working hours (24h local) and a mid-day break.
CLINIC_OPEN_HOUR = 8       # 08:00
CLINIC_CLOSE_HOUR = 22     # 22:00 (last booking must be before close)
CLINIC_BREAK_START = 13    # 13:00
CLINIC_BREAK_END = 16      # 16:00 (afternoon break — common in Oman clinics)
APPOINTMENT_LEAD_MINUTES = 30  # book "now + 30 minutes" when open
NEXT_DAY_MORNING_HOUR = 8      # fallback slot next morning

SERVICE_PORT = int(os.getenv("AI_SERVICE_PORT", "8000"))
