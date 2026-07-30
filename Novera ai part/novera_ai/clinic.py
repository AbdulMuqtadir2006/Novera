"""Badr Al Samaa (Al Khuwair) scheduling logic + location.

Booking rule (per spec):
- If the clinic is open and the doctor is NOT on break: book now + 30 minutes.
- If the doctor is currently on break: book next day at 08:00.
- If now+30 would fall inside the break or after closing: roll to next day 08:00.
- Before opening: book today at 08:00.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from . import config


def _is_break(hour: int) -> bool:
    return config.CLINIC_BREAK_START <= hour < config.CLINIC_BREAK_END


def _next_morning(now: datetime) -> datetime:
    nxt = now + timedelta(days=1)
    return nxt.replace(hour=config.NEXT_DAY_MORNING_HOUR, minute=0, second=0, microsecond=0)


def compute_slot(now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now()
    hour = now.hour

    if _is_break(hour):
        slot = _next_morning(now)
        reason = "doctor_on_break"
    elif hour < config.CLINIC_OPEN_HOUR:
        slot = now.replace(hour=config.CLINIC_OPEN_HOUR, minute=0, second=0, microsecond=0)
        reason = "before_opening"
    elif hour >= config.CLINIC_CLOSE_HOUR:
        slot = _next_morning(now)
        reason = "after_closing"
    else:
        candidate = now + timedelta(minutes=config.APPOINTMENT_LEAD_MINUTES)
        if _is_break(candidate.hour) or candidate.hour >= config.CLINIC_CLOSE_HOUR:
            slot = _next_morning(now)
            reason = "slot_rolls_into_break_or_close"
        else:
            slot = candidate.replace(second=0, microsecond=0)
            reason = "next_available_30min"

    return {
        "when_iso": slot.isoformat(timespec="minutes"),
        "when_human": slot.strftime("%A, %d %b %Y at %I:%M %p"),
        "reason": reason,
        "clinic": config.CLINIC_NAME,
        "branch": config.CLINIC_BRANCH,
    }


def location() -> dict[str, Any]:
    return {
        "name": config.CLINIC_NAME,
        "branch": config.CLINIC_BRANCH,
        "address": config.CLINIC_ADDRESS,
        "maps_url": config.CLINIC_MAPS_URL,
        "phone": config.CLINIC_PHONE,
    }
