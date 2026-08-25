"""ESP32 sensor node status + on-demand sample requests.

The ESP32 can only make outbound requests, so it can't be pushed to directly.
Instead it polls /device/ping every few seconds, reporting its SSID as a
heartbeat and getting back whether the dashboard has requested a fresh
sample — and, when it has, that patient's name (2026-08-24, for the TFT
display added to hardware/esp32_sensor.ino), so the device can show whose
test this is without a second round-trip. Online/offline is derived from
how recently that heartbeat landed, not a persistent connection.

Multi-tenant (2026-08-19): one physical shared device, no inherent per-reading
owner — pending_sample_user_id records who armed it for the next capture, so
routers/readings.py's POST /readings knows whose data the resulting reading
is. Arming itself lives in core/device_control.py (not here) so
core/whatsapp_agent.py's request_sensor_reading tool can reuse it directly
without a core/ -> routers/ import (wrong layering direction).
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from .. import db
from ..core import demo_account
from ..core.device_control import arm_device_for_user, device_state
from ..deps import require_device_key, require_user
from ..schemas import DevicePingIn

router = APIRouter()


@router.post("/device/ping", dependencies=[Depends(require_device_key)])
def ping(body: DevicePingIn):
    row = db.fetch_one(
        """
        UPDATE device_state
        SET ssid = %s, last_seen = %s
        WHERE id = 1
        RETURNING pending_sample, pending_sample_user_id
        """,
        (body.ssid, datetime.now(timezone.utc)),
    )
    pending = bool(row and row["pending_sample"])
    # patient_name (2026-08-24): only meaningful alongside pending=true — a
    # periodic un-requested capture cycle has no pending_sample_user_id, so
    # the firmware correctly has no name to show for that case either.
    # First name only (2026-08-25, Hassan's call) — the small TFT only has
    # room for a short name; shared by both the WhatsApp arm flow and the
    # dashboard's "Take New Sample" button, since both call the same
    # arm_device_for_user() and land here through the same ping().
    patient_name = None
    if pending and row["pending_sample_user_id"]:
        user_row = db.fetch_one("SELECT name FROM users WHERE id = %s", (row["pending_sample_user_id"],))
        if user_row and user_row["name"]:
            patient_name = user_row["name"].strip().split(" ")[0]
    return {"pending_sample": pending, "patient_name": patient_name}


@router.get("/device/status")
def status(user: dict = Depends(require_user)):
    return device_state()


@router.post("/device/request-sample", status_code=202)
def request_sample(user: dict = Depends(require_user)):
    # Bug fix (2026-08-23, Hassan's report): this used to arm the device
    # unconditionally even when it was offline — the request just sat
    # pending with no feedback until the frontend's 30s poll timed out with
    # a generic "no response" message. Now fails fast and honestly, except
    # for the admin/demo account, which is explicitly meant to work with no
    # real sensor connected at all (see core/demo_account.py).
    if not demo_account.is_admin_account(user["id"]) and not device_state()["online"]:
        raise HTTPException(status_code=409, detail="device_offline")
    arm_device_for_user(user["id"])
    return {"requested": True}
