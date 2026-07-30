from __future__ import annotations

import random
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from .. import db
from ..core import reference_data
from ..schemas import ReadingIn

router = APIRouter()


def _round(v: float, dp: int) -> float:
    f = 10**dp
    return round(v * f) / f


def _jitter(base: float, amp: float, dp: int) -> float:
    return _round(base + (random.random() - 0.5) * amp, dp)


@router.get("/readings/latest")
def latest():
    row = reference_data.get_latest_row()
    if not row:
        raise HTTPException(status_code=404, detail="no readings")
    return reference_data.row_to_reading(row)


@router.get("/readings")
def history(days: int = 30):
    days = max(1, min(365, days))
    rows = db.fetch_all(
        'SELECT * FROM readings ORDER BY "timestamp" DESC, id DESC LIMIT %s',
        (days,),
    )
    return [reference_data.row_to_reading(r) for r in reversed(rows)]


@router.post("/readings", status_code=201)
def add_reading(body: ReadingIn):
    """Simulates a fresh sample landing in the DB (optional body values;
    otherwise generate a plausible reading near the last one)."""
    last = reference_data.get_latest_row()
    reading = {
        "ph": body.ph if body.ph is not None else _jitter(last["ph"] if last else 6.8, 0.6, 2),
        "creatinine": body.creatinine if body.creatinine is not None else _jitter(last["creatinine"] if last else 1.0, 0.4, 2),
        "urea": body.urea if body.urea is not None else _jitter(last["urea"] if last else 22, 8, 1),
        "temperature": body.temperature if body.temperature is not None else _jitter(last["temperature"] if last else 36.9, 0.6, 1),
    }
    row = db.fetch_one(
        """
        INSERT INTO readings ("timestamp", ph, creatinine, urea, temperature)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING *
        """,
        (datetime.now(timezone.utc), reading["ph"], reading["creatinine"], reading["urea"], reading["temperature"]),
    )
    return reference_data.row_to_reading(row)
