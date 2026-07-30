"""Shared NoveraState + reference ranges, thresholds, and constants.

Every agent reads and writes this single shared state (Section 5 of the brief).
"""
from __future__ import annotations

from operator import add
from typing import Annotated, Any, Optional, TypedDict

HEALTH_AREAS = ("Kidney Health", "Hydration", "Oral Health", "Digestive Health")
BIOMARKERS = ("ph", "creatinine", "urea", "temperature")

DISCLAIMER = (
    "Novera is a health screening tool, not a medical diagnosis. "
    "Consult a healthcare professional for medical advice."
)

# Sensor-calibrated reference ranges (saliva). NOTE (brief §13.9): these are
# placeholders aligned to the web app's calibration — replace with the real
# biosensor ranges before any live screening.
REFERENCE = {
    "ph": {"range": [6.2, 7.6], "unit": ""},
    "creatinine": {"range": [0.6, 1.3], "unit": "mg/dL"},
    "urea": {"range": [7.0, 20.0], "unit": "mg/dL"},
    "temperature": {"range": [36.1, 37.2], "unit": "°C"},
}

# Which biomarkers drive each health area.
AREA_MARKERS = {
    "Kidney Health": ("creatinine", "urea"),
    "Hydration": ("urea",),
    "Oral Health": ("ph",),
    "Digestive Health": ("ph", "temperature"),
}

# HARDCODED clinical safety gate (brief §4, §6 Analysis). Deterministic — never
# set by an LLM. Placeholder values in the web app's units.
THRESHOLDS = {
    "creatinine_high": 1.7,   # mg/dL
    "urea_high": 26.0,        # mg/dL
    "ph_low": 5.5,
    "ph_high": 8.0,
    "temperature_high": 38.5,  # °C
}


def check_threshold(reading: dict[str, float]) -> tuple[bool, dict[str, Any]]:
    """The hardcoded safety gate. Runs after LLM analysis, sets threshold_crossed.

    Returns (crossed, details). Deterministic and guaranteed every run.
    """
    ph = float(reading.get("ph", 7))
    checks = [
        ("creatinine", float(reading.get("creatinine", 0)), ">", THRESHOLDS["creatinine_high"]),
        ("urea", float(reading.get("urea", 0)), ">", THRESHOLDS["urea_high"]),
        ("temperature", float(reading.get("temperature", 36)), ">", THRESHOLDS["temperature_high"]),
        ("ph", ph, ">", THRESHOLDS["ph_high"]),
        ("ph_low", ph, "<", THRESHOLDS["ph_low"]),
    ]
    for name, value, op, limit in checks:
        crossed = value > limit if op == ">" else value < limit
        if crossed:
            return True, {
                "biomarker": name.replace("_low", ""),
                "value": round(value, 2),
                "threshold": limit,
                "direction": "above" if op == ">" else "below",
            }
    return False, {}


class NoveraState(TypedDict, total=False):
    # Raw input
    user_id: str
    raw_reading: dict  # {"ph","creatinine","urea","temperature"}

    # Quality control
    confidence_score: float
    confidence_reason: str
    qa_loop_count: int
    qa_passed: bool

    # Analysis
    analysis_results: dict
    flagged_domains: list
    threshold_crossed: bool          # set by check_threshold() only
    threshold_details: dict

    # User context (from DB)
    user_context: dict               # {name, phone, language, diet, exercise, age}

    # Outputs
    insight_text: str
    guidance_plan: str
    voice_script: str
    report_path: str

    # WhatsApp flow
    whatsapp_message_sent: bool
    whatsapp_reply: str
    whatsapp_intent: str
    appointment_booked: bool
    appointment_details: dict

    # Language
    detected_language: str
    language_switched: bool

    # Internal routing + observability
    reading_id: str
    error: str
    _route_after_qa: str             # "analysis" | "capture" (set by the Boss node)
    trace: Annotated[list, add]      # append-only node/decision log
