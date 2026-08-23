"""Dashboard biomarker reference ranges + status logic.

Ported 1:1 from the old Node backend's server/health.js — this is the
source of truth for how a raw dashboard `readings` row becomes the shape
the frontend expects (metrics + healthAreas).
"""
from __future__ import annotations

import json
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
        # Multi-tenant (2026-08-19) — carried through so whatsapp_agent.py's
        # sensor.reading_received trigger knows which single user to screen/
        # notify, without a second DB round trip. None for an orphaned/
        # unrequested capture (see routers/readings.py's POST /readings).
        "user_id": row.get("user_id"),
        "timestamp": timestamp.isoformat() if hasattr(timestamp, "isoformat") else timestamp,
        "metrics": metrics,
        "healthAreas": health_areas,
    }


def get_latest_row(user_id: int) -> Optional[dict[str, Any]]:
    """Multi-tenant (2026-08-19): scoped to this user only — a reading with
    user_id IS NULL (orphaned, unrequested capture) never shows up here for
    anyone, by design.

    Admin/demo auto-seed (2026-08-23): if this comes back empty, a local
    (not module-level, to avoid a demo_account <-> reading_synthesis <->
    reference_data import cycle) import checks whether user_id is the
    configured admin account — see core/demo_account.py. A no-op for every
    other account; costs nothing when config.ADMIN_EMAIL is unset."""
    row = db.fetch_one(
        'SELECT * FROM readings WHERE user_id = %s ORDER BY "timestamp" DESC, id DESC LIMIT 1',
        (user_id,),
    )
    if row is None:
        from . import demo_account
        row = demo_account.ensure_seeded(user_id)
    return row


def get_reading_history(user_id: int, days: int = 30) -> list[dict[str, Any]]:
    """Oldest -> newest, same shape as GET /api/readings. Used by report_agent's
    get_reading_history tool so a report can reference a trend instead of only
    ever seeing the single latest reading. Same admin/demo auto-seed as
    get_latest_row above."""
    days = max(1, min(365, days))
    rows = db.fetch_all(
        'SELECT * FROM readings WHERE user_id = %s ORDER BY "timestamp" DESC, id DESC LIMIT %s',
        (user_id, days),
    )
    if not rows:
        from . import demo_account
        seeded = demo_account.ensure_seeded(user_id)
        if seeded:
            rows = [seeded]
    return [row_to_reading(r) for r in reversed(rows)]


def get_context(user_id: int) -> dict[str, Any]:
    """Fetch-or-create — same upsert shape as whatsapp_context.get_or_create()
    so a brand-new account gets an empty-but-real row instead of a 404/None."""
    row = db.fetch_one(
        """
        INSERT INTO patient_context (user_id, diagnosis, medications, notes, updated_at)
        VALUES (%s, '', '', '', now())
        ON CONFLICT (user_id) DO UPDATE SET user_id = EXCLUDED.user_id
        RETURNING diagnosis, medications, notes, updated_at
        """,
        (user_id,),
    )
    return row or {"diagnosis": "", "medications": "", "notes": ""}


def get_chat_history(user_id: int) -> list[dict[str, Any]]:
    return db.fetch_all(
        "SELECT role, content, lang, created_at FROM chat_messages WHERE user_id = %s ORDER BY id ASC",
        (user_id,),
    )


def get_self_care_plan(user_id: int) -> Optional[dict[str, Any]]:
    """The persisted self-care plan for this user, or None if one has never
    been generated. Lets `POST /api/self-care` return instantly for "show me
    what I already have" instead of always re-running the LLM."""
    row = db.fetch_one("SELECT plan_json FROM self_care_plan WHERE user_id = %s", (user_id,))
    if not row or not row.get("plan_json"):
        return None
    plan = row["plan_json"]
    return plan if isinstance(plan, dict) else json.loads(plan)
