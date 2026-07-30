"""Badr Al Samaa (Al Khuwair) scheduling rules — Asia/Muscat (req 14).

Booking rule (unchanged from the original spec):
- Clinic open, doctor NOT on break: candidate = now + 30 minutes, rounded up
  to the next 30-minute slot boundary.
- Doctor currently on break, or the candidate would land in the break / after
  closing: roll to next day 08:00.
- Before opening: book today at 08:00.

This module only computes *candidate* slots — it knows nothing about what's
already booked. core/booking.py layers the double-booking check on top.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .. import config

TZ = ZoneInfo(config.CLINIC_TZ)


def now() -> datetime:
    return datetime.now(TZ)


def _is_break(hour: int) -> bool:
    return config.CLINIC_BREAK_START <= hour < config.CLINIC_BREAK_END


def _next_morning(dt: datetime) -> datetime:
    nxt = dt + timedelta(days=1)
    return nxt.replace(hour=config.NEXT_DAY_MORNING_HOUR, minute=0, second=0, microsecond=0)


def _round_up_to_slot(dt: datetime) -> datetime:
    dt = dt.replace(second=0, microsecond=0)
    remainder = dt.minute % config.SLOT_MINUTES
    if remainder == 0:
        return dt
    return dt + timedelta(minutes=config.SLOT_MINUTES - remainder)


def first_candidate_slot(base: datetime | None = None) -> tuple[datetime, str]:
    """The clinic's first-choice slot per the booking rule, before checking availability."""
    base = base or now()
    hour = base.hour

    if _is_break(hour):
        return _next_morning(base), "doctor_on_break"
    if hour < config.CLINIC_OPEN_HOUR:
        return base.replace(hour=config.CLINIC_OPEN_HOUR, minute=0, second=0, microsecond=0), "before_opening"
    if hour >= config.CLINIC_CLOSE_HOUR:
        return _next_morning(base), "after_closing"

    candidate = _round_up_to_slot(base + timedelta(minutes=config.APPOINTMENT_LEAD_MINUTES))
    if _is_break(candidate.hour) or candidate.hour >= config.CLINIC_CLOSE_HOUR:
        return _next_morning(base), "slot_rolls_into_break_or_close"
    return candidate, "next_available_30min"


def next_slot(current: datetime) -> datetime:
    """Advance one 30-minute slot, rolling into the next valid opening window."""
    candidate = current + timedelta(minutes=config.SLOT_MINUTES)
    if _is_break(candidate.hour) or candidate.hour >= config.CLINIC_CLOSE_HOUR:
        return _next_morning(candidate)
    if candidate.hour < config.CLINIC_OPEN_HOUR:
        return candidate.replace(hour=config.CLINIC_OPEN_HOUR, minute=0, second=0, microsecond=0)
    return candidate


def location() -> dict[str, Any]:
    return {
        "name": config.CLINIC_NAME,
        "branch": config.CLINIC_BRANCH,
        "address": config.CLINIC_ADDRESS,
        "maps_url": config.CLINIC_MAPS_URL,
        "phone": config.CLINIC_PHONE,
    }
