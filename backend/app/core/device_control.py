"""Shared-device arming — the one physical ESP32 has no inherent per-reading
owner (multi-tenant migration, 2026-08-19), so something has to say "the next
capture is for user X" before it happens. Used directly (no HTTP round-trip)
by both routers/device.py's POST /device/request-sample and
core/whatsapp_agent.py's request_sensor_reading tool.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .. import db

logger = logging.getLogger(__name__)

# Single source of truth for "is the ESP32 online" (2026-08-23) — previously
# duplicated inline in routers/device.py's status() only, so nothing else
# (the WhatsApp request_sensor_reading tool, the request-sample endpoint)
# could check it before arming an offline device, which just silently sat
# pending until/unless the device ever came back.
ONLINE_WINDOW_SECONDS = 15


def device_state() -> dict[str, Any]:
    """Current {ssid, online} — online means a /device/ping heartbeat landed
    within the last ONLINE_WINDOW_SECONDS."""
    row = db.fetch_one("SELECT ssid, last_seen FROM device_state WHERE id = 1")
    last_seen = row["last_seen"] if row else None
    online = bool(
        last_seen
        and (datetime.now(timezone.utc) - last_seen).total_seconds() < ONLINE_WINDOW_SECONDS
    )
    return {"ssid": (row["ssid"] if row else None) if online else None, "online": online}


def arm_device_for_user(user_id: int) -> None:
    db.execute(
        "UPDATE device_state SET pending_sample = true, pending_sample_user_id = %s WHERE id = 1",
        (user_id,),
    )
    logger.info("device_control: armed device for user_id=%s", user_id)
