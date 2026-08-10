"""Central configuration for the NOVERA backend. Everything comes from the
environment — nothing here is ever a real secret (req 17)."""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# ---- database ----
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# ---- OpenRouter (via ChatOpenAI) ----
# Two models, split by stakes: cheap/high-volume content generation on DeepSeek,
# the single screening decision call on Claude (accuracy matters more than cost there).
# DeepSeek default pinned to a dated snapshot (not a "-latest" floating alias)
# so behavior doesn't shift under us; v3.1 was retired from OpenRouter's
# catalog, migrated to the v4 Flash generation.
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL_CONTENT = os.getenv("OPENROUTER_MODEL_CONTENT", "deepseek/deepseek-v4-flash-0731").strip()
OPENROUTER_MODEL_SCREENING = os.getenv("OPENROUTER_MODEL_SCREENING", "anthropic/claude-sonnet-5").strip()
OPENROUTER_TIMEOUT_SECONDS = max(15, int(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "60")))
AI_ENABLED = bool(OPENROUTER_API_KEY.startswith("sk-or-"))

CONFIRMED_CASE_QUERY_LIMIT = max(3, int(os.getenv("CONFIRMED_CASE_QUERY_LIMIT", "25")))

# ---- WhatsApp — Meta (Facebook) Cloud API ----
META_WHATSAPP_TOKEN = os.getenv("META_WHATSAPP_TOKEN", "").strip()
META_PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID", "").strip()
META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "").strip()
META_APP_SECRET = os.getenv("META_APP_SECRET", "").strip()
META_API_VERSION = os.getenv("META_API_VERSION", "v22.0").strip() or "v22.0"
WHATSAPP_TO = os.getenv("WHATSAPP_TO", "").strip()
WHATSAPP_ENABLED = bool(META_WHATSAPP_TOKEN and META_PHONE_NUMBER_ID)

# ---- clinic — Badr Al Samaa, Al Khuwair (Muscat) ----
CLINIC_TZ = "Asia/Muscat"
CLINIC_NAME = "Badr Al Samaa"
CLINIC_BRANCH = "Al Khuwair"
CLINIC_ADDRESS = "Badr Al Samaa Medical Centre, Al Khuwair, Muscat, Oman"
CLINIC_MAPS_URL = "https://maps.google.com/?q=Badr+Al+Samaa+Al+Khuwair+Muscat"
CLINIC_PHONE = "+968 2479 8800"

CLINIC_OPEN_HOUR = 8       # 08:00
CLINIC_CLOSE_HOUR = 22     # 22:00 (last booking must be before close)
CLINIC_BREAK_START = 13    # 13:00
CLINIC_BREAK_END = 16      # 16:00
APPOINTMENT_LEAD_MINUTES = 30
SLOT_MINUTES = 30
NEXT_DAY_MORNING_HOUR = 8

# ---- CORS (req 15) ----
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "https://www.echo-nova.online,https://echo-nova.online,"
        "http://localhost:5173,http://127.0.0.1:5173,"
        # Capacitor's Android WebView serves the bundled app from this
        # virtual origin by default (server.androidScheme, unset = https).
        "https://localhost",
    ).split(",")
    if origin.strip()
]

# ---- misc ----
SERVICE_PORT = int(os.getenv("PORT", "8000"))
