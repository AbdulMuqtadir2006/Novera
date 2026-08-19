"""ESP32 sensor node status + on-demand sample requests.

The ESP32 can only make outbound requests, so it can't be pushed to directly.
Instead it polls /device/ping every few seconds, reporting its SSID as a
heartbeat and getting back whether the dashboard has requested a fresh
sample. Online/offline is derived from how recently that heartbeat landed,
not a persistent connection.

Multi-tenant (2026-08-19): one physical shared device, no inherent per-reading
owner — pending_sample_user_id records who armed it for the next capture, so
routers/readings.py's POST /readings knows whose data the resulting reading
is. Arming itself lives in core/device_control.py (not here) so
core/whatsapp_agent.py's request_sensor_reading tool can reuse it directly
without a core/ -> routers/ import (wrong layering direction).
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from .. import db
from ..core.device_control import arm_device_for_user
from ..deps import require_user
from ..schemas import DevicePingIn

router = APIRouter()

ONLINE_WINDOW_SECONDS = 15


@router.post("/device/ping")
def ping(body: DevicePingIn):
    row = db.fetch_one(
        """
        UPDATE device_state
        SET ssid = %s, last_seen = %s
        WHERE id = 1
        RETURNING pending_sample
        """,
        (body.ssid, datetime.now(timezone.utc)),
    )
    return {"pending_sample": bool(row and row["pending_sample"])}


@router.get("/device/status")
def status():
    row = db.fetch_one("SELECT ssid, last_seen FROM device_state WHERE id = 1")
    last_seen = row["last_seen"] if row else None
    online = bool(
        last_seen
        and (datetime.now(timezone.utc) - last_seen).total_seconds() < ONLINE_WINDOW_SECONDS
    )
    return {"ssid": (row["ssid"] if row else None) if online else None, "online": online}


@router.post("/device/request-sample", status_code=202)
def request_sample(user: dict = Depends(require_user)):
    arm_device_for_user(user["id"])
    return {"requested": True}
