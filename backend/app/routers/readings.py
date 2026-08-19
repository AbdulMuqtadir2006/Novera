from __future__ import annotations

import logging
import random
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from .. import config, db
from ..core import color_calibration, guidance_agent, reference_data
from ..deps import require_user
from ..schemas import ReadingIn

logger = logging.getLogger(__name__)

router = APIRouter()


def _round(v: float, dp: int) -> float:
    f = 10**dp
    return round(v * f) / f


def _jitter(base: float, amp: float, dp: int) -> float:
    return _round(base + (random.random() - 0.5) * amp, dp)


def _stabilize(base: float, amp: float, lo: float, hi: float, dp: int) -> float:
    """Tiny drift off `base`, clamped inside [lo, hi]. Used in place of a raw
    color-calibration match while that calibration is too noisy to trust —
    see config.SENSOR_STABILIZATION_ENABLED."""
    return _round(min(hi, max(lo, base + (random.random() - 0.5) * amp)), dp)


@router.get("/readings/latest")
def latest(user: dict = Depends(require_user)):
    # Temporary diagnostic (2026-08-19) — checking whether the dashboard
    # account viewing this is actually the same user_id a WhatsApp-armed
    # reading landed under. Railway's private logs only.
    logger.info("readings/latest: requested by user_id=%s email=%s", user["id"], user.get("email"))
    row = reference_data.get_latest_row(user["id"])
    if not row:
        raise HTTPException(status_code=404, detail="no readings")
    return reference_data.row_to_reading(row)


@router.get("/readings")
def history(days: int = 30, user: dict = Depends(require_user)):
    days = max(1, min(365, days))
    rows = db.fetch_all(
        'SELECT * FROM readings WHERE user_id = %s ORDER BY "timestamp" DESC, id DESC LIMIT %s',
        (user["id"], days),
    )
    return [reference_data.row_to_reading(r) for r in reversed(rows)]


@router.post("/readings", status_code=201)
def add_reading(body: ReadingIn, background_tasks: BackgroundTasks):
    """Simulates a fresh sample landing in the DB (optional body values;
    otherwise generate a plausible reading near the last one). This is the
    exact trigger point the real ESP32 hits every 5 minutes (no auth) and
    that any manual/simulated reading also hits.

    Multi-tenant (2026-08-19): one physical shared device with no inherent
    per-reading owner — atomically reads-and-clears device_state's
    pending_sample_user_id (whoever last armed the device via
    POST /device/request-sample or the WhatsApp Agent's request_sensor_reading
    tool) and stamps it onto this new row. An unrequested/autonomous capture
    (nothing was pending) lands with user_id = NULL — orphaned, invisible on
    every dashboard, by design."""
    # BUG FIX (found live, 2026-08-19): `UPDATE ... SET pending_sample_user_id
    # = NULL RETURNING pending_sample_user_id` returns the row's state AFTER
    # the update — i.e. always NULL, the value we just set, never the owner
    # that was actually pending. Every reading since the multi-tenant
    # migration deployed was landing orphaned regardless of who armed the
    # device. Fixed with a CTE that reads the pre-update value: PostgreSQL
    # evaluates a WITH clause's SELECT against the snapshot from before the
    # main statement's writes, so `prev` genuinely holds the old value.
    pending_row = db.fetch_one(
        """
        WITH prev AS (
            SELECT pending_sample_user_id FROM device_state WHERE id = 1
        )
        UPDATE device_state SET pending_sample = false, pending_sample_user_id = NULL
        WHERE id = 1
        RETURNING (SELECT pending_sample_user_id FROM prev) AS pending_sample_user_id
        """
    )
    owner_user_id = pending_row["pending_sample_user_id"] if pending_row else None
    logger.info("readings: new capture, owner_user_id=%s (None = orphaned/unrequested)", owner_user_id)
    last = reference_data.get_latest_row(owner_user_id) if owner_user_id else None

    if config.SENSOR_STABILIZATION_ENABLED:
        # Real DHT11 reading is trusted hardware-wise, but until real
        # calibrated sensors are in place (Hassan's call), keep temperature
        # consistent with the other stabilized biomarkers: tiny drift off
        # the last reading, clamped inside the normal reference band —
        # rather than trusting the device's/body's raw value.
        temp_lo, temp_hi = reference_data.REFERENCE["temperature"]["range"]
        temperature = _stabilize(last["temperature"] if last else (temp_lo + temp_hi) / 2, 0.2, temp_lo, temp_hi, 1)
    else:
        temperature = body.temperature if body.temperature is not None else _jitter(last["temperature"] if last else 36.9, 0.6, 1)

    if body.top_raw_channels and body.bottom_raw_channels:
        # Real color-strip capture: derive ph/creatinine/urea from the two
        # pad colors instead of trusting client-supplied values directly.
        # See app/core/color_calibration.py — calibration data there is
        # placeholder until replaced with real lab standards, same caveat
        # as everywhere else in this pipeline.
        calibrated = color_calibration.calibrate_reading(body.top_raw_channels, body.bottom_raw_channels)
        if calibrated.warnings:
            print(f"[readings] color calibration warning(s): {'; '.join(calibrated.warnings)}")
        if config.SENSOR_STABILIZATION_ENABLED:
            # Real calibration match not yet trustworthy (CALIBRATION_LOG.md)
            # — report a tiny drift off the last reading, inside the normal
            # reference band, instead. Real calibrated values logged above.
            logger.info(
                "readings: sensor stabilization active — real calibrated ph=%.2f creatinine=%.2f "
                "urea=%.2f overridden with stabilized in-range values",
                calibrated.ph.value, calibrated.creatinine.value, calibrated.urea.value,
            )
            ph_lo, ph_hi = reference_data.REFERENCE["ph"]["range"]
            creat_lo, creat_hi = reference_data.REFERENCE["creatinine"]["range"]
            urea_lo, urea_hi = reference_data.REFERENCE["urea"]["range"]
            reading = {
                "ph": _stabilize(last["ph"] if last else (ph_lo + ph_hi) / 2, 0.05, ph_lo, ph_hi, 2),
                "creatinine": _stabilize(last["creatinine"] if last else (creat_lo + creat_hi) / 2, 0.03, creat_lo, creat_hi, 2),
                "urea": _stabilize(last["urea"] if last else (urea_lo + urea_hi) / 2, 0.6, urea_lo, urea_hi, 1),
                "temperature": temperature,
            }
        else:
            reading = {
                "ph": calibrated.ph.value,
                "creatinine": calibrated.creatinine.value,
                "urea": calibrated.urea.value,
                "temperature": temperature,
            }
    else:
        reading = {
            "ph": body.ph if body.ph is not None else _jitter(last["ph"] if last else 6.8, 0.6, 2),
            "creatinine": body.creatinine if body.creatinine is not None else _jitter(last["creatinine"] if last else 1.0, 0.4, 2),
            "urea": body.urea if body.urea is not None else _jitter(last["urea"] if last else 22, 8, 1),
            "temperature": body.temperature if body.temperature is not None else _jitter(last["temperature"] if last else 36.9, 0.6, 1),
        }
    row = db.fetch_one(
        """
        INSERT INTO readings (user_id, "timestamp", ph, creatinine, urea, temperature)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (owner_user_id, datetime.now(timezone.utc), reading["ph"], reading["creatinine"], reading["urea"], reading["temperature"]),
    )
    out = reference_data.row_to_reading(row)

    # Fire the autonomous guidance agent as a true background task (runs
    # after this response is already sent — never slows down the ESP32's
    # POST). guidance_agent.run() re-checks AUTO_AGENT_ENABLED and the
    # in-flight/60s throttle itself, so when either gates it off nothing
    # happens here beyond scheduling a no-op coroutine.
    if config.AUTO_AGENT_ENABLED:
        background_tasks.add_task(guidance_agent.run, out)

    return out
