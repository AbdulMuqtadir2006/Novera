"""Postgres-backed appointment booking — the only place bookings are written.

Double-booking prevention (req 14): `appointments.slot_start` has a UNIQUE
constraint; booking a slot is `INSERT ... ON CONFLICT (slot_start) DO NOTHING
RETURNING ...`. If the slot's taken (by a prior booking or a concurrent
request that wins the race), we advance to the next 30-minute slot and try
again, bounded to a generous search window. LangGraph/LLM code never calls
this with an invented time — it only ever asks for "the next available slot".
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from .. import config, db
from . import clinic

MAX_SLOT_ATTEMPTS = 96  # ~2 days of 30-minute slots — generous upper bound


def _row_to_booking(row: dict[str, Any], reason: str = "") -> dict[str, Any]:
    slot: datetime = row["slot_start"]
    booked_at = row.get("booked_at")
    return {
        "id": row["id"],
        "when_iso": slot.isoformat(timespec="minutes"),
        "when_human": slot.strftime("%A, %d %b %Y at %I:%M %p"),
        "reason": row.get("reason") or reason,
        "clinic": row.get("clinic") or config.CLINIC_NAME,
        "branch": row.get("branch") or config.CLINIC_BRANCH,
        "channel": row.get("channel"),
        "booked_at": booked_at.isoformat() if hasattr(booked_at, "isoformat") else booked_at,
        "location": clinic.location(),
    }


def find_and_book_slot(
    user_id: Optional[int] = None,
    phone: Optional[str] = None,
    channel: str = "whatsapp",
) -> dict[str, Any]:
    """Find the next free 30-minute slot (Asia/Muscat, now+30min, clinic hours
    respected) and book it. Retries forward through the slot grid on conflict."""
    slot, reason = clinic.first_candidate_slot()

    for _ in range(MAX_SLOT_ATTEMPTS):
        row = db.fetch_one(
            """
            INSERT INTO appointments (user_id, phone, slot_start, reason, clinic, branch, channel)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (slot_start) DO NOTHING
            RETURNING id, slot_start, reason, clinic, branch, channel, booked_at
            """,
            (user_id, phone, slot, reason, config.CLINIC_NAME, config.CLINIC_BRANCH, channel),
        )
        if row:
            return _row_to_booking(row)
        slot = clinic.next_slot(slot)
        reason = "next_available_30min"

    raise RuntimeError("No available appointment slot found within the search window.")


def list_bookings(limit: int = 50) -> list[dict[str, Any]]:
    rows = db.fetch_all(
        """
        SELECT id, slot_start, reason, clinic, branch, channel, booked_at
        FROM appointments
        ORDER BY slot_start DESC
        LIMIT %s
        """,
        (limit,),
    )
    return [_row_to_booking(row) for row in rows]


def list_upcoming_for_user(user_id: int, limit: int = 5) -> list[dict[str, Any]]:
    rows = db.fetch_all(
        """
        SELECT id, slot_start, reason, clinic, branch, channel, booked_at
        FROM appointments
        WHERE user_id = %s AND slot_start >= now()
        ORDER BY slot_start ASC
        LIMIT %s
        """,
        (user_id, limit),
    )
    return [_row_to_booking(row) for row in rows]


def list_upcoming_for_phone(phone: str, limit: int = 5) -> list[dict[str, Any]]:
    rows = db.fetch_all(
        """
        SELECT id, slot_start, reason, clinic, branch, channel, booked_at
        FROM appointments
        WHERE phone = %s AND slot_start >= now()
        ORDER BY slot_start ASC
        LIMIT %s
        """,
        (phone, limit),
    )
    return [_row_to_booking(row) for row in rows]
