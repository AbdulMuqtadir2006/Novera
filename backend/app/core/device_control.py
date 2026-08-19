"""Shared-device arming — the one physical ESP32 has no inherent per-reading
owner (multi-tenant migration, 2026-08-19), so something has to say "the next
capture is for user X" before it happens. Used directly (no HTTP round-trip)
by both routers/device.py's POST /device/request-sample and
core/whatsapp_agent.py's request_sensor_reading tool.
"""
from __future__ import annotations

from .. import db


def arm_device_for_user(user_id: int) -> None:
    db.execute(
        "UPDATE device_state SET pending_sample = true, pending_sample_user_id = %s WHERE id = 1",
        (user_id,),
    )
