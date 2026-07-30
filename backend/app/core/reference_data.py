"""Dashboard biomarker reference ranges + status logic.

Ported 1:1 from the old Node backend's server/health.js — this is the
source of truth for how a raw dashboard `readings` row becomes the shape
the frontend expects (metrics + healthAreas).
"""
from __future__ import annotations

from typing import Any, Optional

from .. import db

REFERENCE: dict[str, dict[str, Any]] = {
    "ph": {"unit": "", "range": [6.2, 7.6], "dp": 2, "label": "pH"},
    "creatinine": {"unit": "mg/dL", "range": [0.6, 1.3], "dp": 2, "label": "Creatinine"},
    "urea": {"unit": "mg/dL", "range": [7, 20], "dp": 1, "label": "Urea"},
    "temperature": {"unit": "°C", "range": [36.1, 37.2], "dp": 1, "label": "Temperature"},
}

_RANK = {"good": 0, "watch": 1, "attention": 2}


def status_for(value: float, range_: list[float], soft_pad: float = 0.12) -> str:
    low, high = range_
    span = high - low
    pad = span * soft_pad
    if value < low - pad or value > high + pad:
        return "attention"
    if value < low or value > high:
        return "watch"
    return "good"


def _worst(a: str, b: str) -> str:
    return a if _RANK[a] >= _RANK[b] else b


def row_to_reading(row: dict[str, Any]) -> dict[str, Any]:
    """Turn a raw `readings` DB row into the shape the frontend expects."""
    metrics: dict[str, Any] = {}
    for key, ref in REFERENCE.items():
        value = row[key]
        metrics[key] = {
            "value": value,
            "unit": ref["unit"],
            "range": ref["range"],
            "status": status_for(value, ref["range"]),
        }
    health_areas = {
        "kidney": _worst(metrics["creatinine"]["status"], metrics["urea"]["status"]),
        "hydration": "good" if metrics["urea"]["status"] == "good" else "watch",
        "oral": metrics["ph"]["status"],
        "digestive": _worst(metrics["ph"]["status"], metrics["temperature"]["status"]),
    }
    timestamp = row["timestamp"]
    return {
        "id": row["id"],
        "timestamp": timestamp.isoformat() if hasattr(timestamp, "isoformat") else timestamp,
        "metrics": metrics,
        "healthAreas": health_areas,
    }


def get_latest_row() -> Optional[dict[str, Any]]:
    return db.fetch_one(
        'SELECT * FROM readings ORDER BY "timestamp" DESC, id DESC LIMIT 1'
    )


def get_context() -> dict[str, Any]:
    row = db.fetch_one(
        "SELECT diagnosis, medications, notes, updated_at FROM patient_context WHERE id = 1"
    )
    return row or {"diagnosis": "", "medications": "", "notes": ""}


def get_chat_history() -> list[dict[str, Any]]:
    return db.fetch_all(
        "SELECT role, content, lang, created_at FROM chat_messages ORDER BY id ASC"
    )
