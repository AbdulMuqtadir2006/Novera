"""The background clock that makes triggers 2-4 possible (spec §3.2) —
without something checking time independently of any request, the WhatsApp
Agent has no way to notice "the appointment passed" or "it's check-in time".
Runs continuously as an asyncio task started at app boot (see main.py).

Scope note (updated 2026-08-19, later same day): every registered account
(family members, testers, etc.) has its own screening/reading data now (see
db/schema.sql's multi-tenant migration) as well as its own WhatsApp Agent
conversation/check-in state — "patients" below means "every registered user
with a phone number," each independently.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .. import config, db
from . import whatsapp_agent

_CLINIC_TZ = ZoneInfo(config.CLINIC_TZ)

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 300  # 5 minutes — cheap, no reason to poll faster

# --- Placeholder timing, not a real product decision (flagging, not hiding
# it — same spirit as spec §8's explicit call-out for wellness cadence,
# extended here to meal check-in timing which the spec didn't give a number
# for either). Change these once there's a real answer, no schema change
# needed for the meal hour; wellness cadence is already a per-row DB field. ---
MEAL_CHECKIN_HOUR_LOCAL = 13  # placeholder: Oman lunchtime, Asia/Muscat local time
APPOINTMENT_FOLLOWUP_LOOKBACK_HOURS = 24 * 7  # don't flood old appointments if the scheduler was ever down


async def _fire_appointment_completed() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=APPOINTMENT_FOLLOWUP_LOOKBACK_HOURS)
    rows = db.fetch_all(
        """
        SELECT a.id, a.user_id, a.reason
        FROM appointments a
        WHERE a.status = 'confirmed'
          AND a.followup_sent = false
          AND a.slot_start < now()
          AND a.slot_start > %s
          AND a.user_id IS NOT NULL
        """,
        (cutoff,),
    )
    for appt in rows:
        user = db.fetch_one("SELECT id, email, name, phone FROM users WHERE id = %s", (appt["user_id"],))
        # Mark it sent immediately, before the agent even runs — the trigger
        # fires once per appointment regardless of whether the model decides
        # to actually send a message (restraint is a send-decision, not a
        # trigger-repeat decision); otherwise a "stayed quiet" run would
        # re-fire on every single 5-minute poll forever.
        db.execute("UPDATE appointments SET followup_sent = true WHERE id = %s", (appt["id"],))
        if not user or not user.get("phone"):
            continue
        try:
            await asyncio.to_thread(
                whatsapp_agent.handle_trigger, "appointment.completed", user, {"appointment_id": appt["id"]},
            )
        except Exception:
            logger.exception("scheduler: appointment.completed trigger failed for appointment_id=%s", appt["id"])


async def _fire_meal_checkins() -> None:
    now_local_hour = datetime.now(_CLINIC_TZ).hour
    if now_local_hour != MEAL_CHECKIN_HOUR_LOCAL:
        return
    rows = db.fetch_all(
        """
        SELECT u.id, u.email, u.name, u.phone
        FROM users u
        JOIN whatsapp_patient_context c ON c.user_id = u.id
        WHERE u.phone <> ''
          AND c.self_care_plan IS NOT NULL
          AND (c.last_meal_checkin_at IS NULL OR c.last_meal_checkin_at < date_trunc('day', now()))
        """
    )
    for user in rows:
        try:
            await asyncio.to_thread(whatsapp_agent.handle_trigger, "mealtime.checkin", user, None)
        except Exception:
            logger.exception("scheduler: mealtime.checkin trigger failed for user_id=%s", user["id"])


async def _fire_wellness_checkins() -> None:
    rows = db.fetch_all(
        """
        SELECT u.id, u.email, u.name, u.phone, c.wellness_checkin_cadence_days
        FROM users u
        JOIN whatsapp_patient_context c ON c.user_id = u.id
        WHERE u.phone <> ''
          AND (
            c.last_wellness_checkin_at IS NULL
            OR c.last_wellness_checkin_at < now() - (c.wellness_checkin_cadence_days || ' days')::interval
          )
        """
    )
    for user in rows:
        try:
            await asyncio.to_thread(whatsapp_agent.handle_trigger, "wellness.checkin", user, None)
        except Exception:
            logger.exception("scheduler: wellness.checkin trigger failed for user_id=%s", user["id"])


async def scheduler_loop() -> None:
    """Runs forever. Each pass is independently try/excepted so one bad poll
    (e.g. a transient DB hiccup) doesn't kill the whole background task —
    the next poll 5 minutes later just tries again."""
    logger.info("scheduler_loop starting, polling every %ss", POLL_INTERVAL_SECONDS)
    while True:
        try:
            await _fire_appointment_completed()
        except Exception:
            logger.exception("scheduler: appointment.completed poll failed")
        try:
            await _fire_meal_checkins()
        except Exception:
            logger.exception("scheduler: mealtime.checkin poll failed")
        try:
            await _fire_wellness_checkins()
        except Exception:
            logger.exception("scheduler: wellness.checkin poll failed")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
