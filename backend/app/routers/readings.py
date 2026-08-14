from __future__ import annotations

import random
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from .. import config, db
from ..core import guidance_agent, reference_data
from ..deps import require_user
from ..schemas import ReadingIn

router = APIRouter()


def _round(v: float, dp: int) -> float:
    f = 10**dp
    return round(v * f) / f


def _jitter(base: float, amp: float, dp: int) -> float:
    return _round(base + (random.random() - 0.5) * amp, dp)


@router.get("/readings/latest")
def latest(user: dict = Depends(require_user)):
    row = reference_data.get_latest_row()
    if not row:
        raise HTTPException(status_code=404, detail="no readings")
    return reference_data.row_to_reading(row)


@router.get("/readings")
def history(days: int = 30, user: dict = Depends(require_user)):
    days = max(1, min(365, days))
    rows = db.fetch_all(
        'SELECT * FROM readings ORDER BY "timestamp" DESC, id DESC LIMIT %s',
        (days,),
    )
    return [reference_data.row_to_reading(r) for r in reversed(rows)]


@router.post("/readings", status_code=201)
def add_reading(body: ReadingIn, background_tasks: BackgroundTasks):
    """Simulates a fresh sample landing in the DB (optional body values;
    otherwise generate a plausible reading near the last one). This is the
    exact trigger point the real ESP32 hits every 5 minutes (no auth) and
    that any manual/simulated reading also hits."""
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
    # Clears any pending on-demand sample request from the dashboard —
    # covers both the ESP32's periodic pushes and its request-triggered ones.
    db.execute("UPDATE device_state SET pending_sample = false WHERE id = 1")
    out = reference_data.row_to_reading(row)

    # Fire the autonomous guidance agent as a true background task (runs
    # after this response is already sent — never slows down the ESP32's
    # POST). guidance_agent.run() re-checks AUTO_AGENT_ENABLED and the
    # in-flight/60s throttle itself, so when either gates it off nothing
    # happens here beyond scheduling a no-op coroutine.
    if config.AUTO_AGENT_ENABLED:
        background_tasks.add_task(guidance_agent.run, out)

    return out
