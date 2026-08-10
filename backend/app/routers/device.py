"""ESP32 sensor node status + on-demand sample requests.

The ESP32 can only make outbound requests, so it can't be pushed to directly.
Instead it polls /device/ping every few seconds, reporting its SSID as a
heartbeat and getting back whether the dashboard has requested a fresh
sample. Online/offline is derived from how recently that heartbeat landed,
not a persistent connection.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from .. import db
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
def request_sample():
    db.execute("UPDATE device_state SET pending_sample = true WHERE id = 1")
    return {"requested": True}
