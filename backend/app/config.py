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

# ---- website (patient-facing signup, linked from the WhatsApp Agent when
# an unregistered number texts in) ----
SIGNUP_URL = os.getenv("SIGNUP_URL", "https://www.echo-nova.online/signup").strip()

# ---- public URLs (for building redirect targets outside the request) ----
PUBLIC_SITE_URL = os.getenv("PUBLIC_SITE_URL", "https://www.echo-nova.online").strip()
PUBLIC_API_URL = os.getenv("PUBLIC_API_URL", "https://api.echo-nova.online").strip()

# ---- Thawani (Oman payment gateway) — device/strip-bundle checkout ----
# No live merchant credentials exist yet — checkout stays honestly disabled
# (routers/orders.py returns 503, never a fake "payment successful") until
# both keys are set. THAWANI_ENV picks Thawani's UAT vs production API base
# (see core/thawani.py) — "development" (UAT, sandbox) by default so this
# can't accidentally go live before someone deliberately flips it.
THAWANI_SECRET_KEY = os.getenv("THAWANI_SECRET_KEY", "").strip()
THAWANI_PUBLISHABLE_KEY = os.getenv("THAWANI_PUBLISHABLE_KEY", "").strip()
THAWANI_ENV = os.getenv("THAWANI_ENV", "development").strip()
THAWANI_ENABLED = bool(THAWANI_SECRET_KEY and THAWANI_PUBLISHABLE_KEY)

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

# ---- autonomous guidance agent orchestrator ----
# Kill switch for the tool-calling orchestrator that fires on every
# POST /api/readings (real ESP32 + simulated readings alike). Default on;
# set AUTO_AGENT_ENABLED=false to fully disable with zero behavior change
# to the readings endpoint. Parsed the same simple way AI_ENABLED is derived
# above — no external bool-parsing helper exists in this codebase yet.
AUTO_AGENT_ENABLED = os.getenv("AUTO_AGENT_ENABLED", "true").strip().lower() != "false"

# ---- sensor stabilization (temporary, until real AS7341 calibration lands) ----
# The real color-strip calibration (color_calibration.py) is not yet reliable
# — acid/neutral don't separate, hand-held noise dominates the signal (see
# hardware/esp32_sensor/CALIBRATION_LOG.md). While this is on, every reading's
# ph/creatinine/urea/temperature are reported as a tiny drift off the
# patient's last reading, clamped inside the normal reference band, instead
# of the raw sensor/calibration value — temperature included per Hassan
# (2026-08-20), pending better hardware, even though DHT11 itself is real.
# The real calibrated color values are still logged either way, so
# calibration work keeps accumulating. Set SENSOR_STABILIZATION_ENABLED=false
# once real calibrated sensors replace the placeholder charts.
SENSOR_STABILIZATION_ENABLED = os.getenv("SENSOR_STABILIZATION_ENABLED", "true").strip().lower() != "false"

# ---- screening flag suppression (temporary, until Hassan says otherwise) ----
# Sensors/calibration aren't trustworthy enough yet to be telling real people
# to get tested or see a doctor (2026-08-20 call). While this is on,
# scoring.ScoringEngine.evaluate() forces every organ's flag to "low" —
# combined_score/range_score/similarity_score are still computed and stored
# for real in decision_audit, only the flag that automation acts on is
# suppressed. This is what mutes whatsapp_gating.enforce_outreach_guarantee's
# forced appointment offer (medium/high only) and any other flag-gated
# messaging. Default ON — set SUPPRESS_SCREENING_FLAGS=false once the
# underlying scoring is trustworthy enough to actually flag people again.
SUPPRESS_SCREENING_FLAGS = os.getenv("SUPPRESS_SCREENING_FLAGS", "true").strip().lower() != "false"

# ---- misc ----
SERVICE_PORT = int(os.getenv("PORT", "8000"))
