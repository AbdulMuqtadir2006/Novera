"""Per-registered-user WhatsApp Agent memory — see
novera-whatsapp-autonomous-agent-spec.md §3.4.

Deliberately narrow: conversation state, the 24h send-window timestamps, and
check-in/self-care tracking. NOT a second copy of appointment status
(appointments is the single source of truth, see booking.py) and NOT the
dashboard's self_care_plan/patient_context tables (a genuinely different
self-care plan than this one — this is what gets generated in-conversation
here, that's what the dashboard shows). CORRECTED 2026-08-19 (same day,
later): screening/reading data used to be described as staying single-
patient/global here — that was reversed within hours. All of
readings/screening_cases/patient_context/self_care_plan/chat_messages are
per-user now (see db/schema.sql's multi-tenant migration).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from .. import db

# Conversation summary is a rolling, bounded string (not a growing
# transcript) — keeps every future trigger's context small regardless of how
# long a patient's relationship with the agent gets. Trimmed to the most
# recent content, oldest first, on every append.
MAX_CONVERSATION_SUMMARY_CHARS = 4000


def get_or_create(user_id: int) -> dict[str, Any]:
    row = db.fetch_one("SELECT * FROM whatsapp_patient_context WHERE user_id = %s", (user_id,))
    if row:
        return row
    return db.fetch_one(
        """
        INSERT INTO whatsapp_patient_context (user_id) VALUES (%s)
        ON CONFLICT (user_id) DO UPDATE SET user_id = EXCLUDED.user_id
        RETURNING *
        """,
        (user_id,),
    )


def within_24h_window(context: dict[str, Any]) -> bool:
    """The hard Meta send-window gate (spec §5) — free-form/voice/document
    sends are only allowed if the patient messaged within the last 24h;
    otherwise only a pre-approved template may be used. Checked in code,
    never left to the model's judgment."""
    last_inbound = context.get("last_inbound_at")
    if not last_inbound:
        return False
    return (datetime.now(timezone.utc) - last_inbound).total_seconds() < 24 * 3600


def mark_inbound(user_id: int) -> None:
    db.execute(
        """
        INSERT INTO whatsapp_patient_context (user_id, last_inbound_at) VALUES (%s, now())
        ON CONFLICT (user_id) DO UPDATE SET last_inbound_at = now(), updated_at = now()
        """,
        (user_id,),
    )


def mark_outbound(user_id: int) -> None:
    db.execute(
        """
        INSERT INTO whatsapp_patient_context (user_id, last_outbound_at) VALUES (%s, now())
        ON CONFLICT (user_id) DO UPDATE SET last_outbound_at = now(), updated_at = now()
        """,
        (user_id,),
    )


def append_conversation_note(user_id: int, note: str) -> None:
    if not note.strip():
        return
    context = get_or_create(user_id)
    combined = (context.get("conversation_summary") or "") + f"\n- {note.strip()}"
    combined = combined[-MAX_CONVERSATION_SUMMARY_CHARS:]
    db.execute(
        "UPDATE whatsapp_patient_context SET conversation_summary = %s, updated_at = now() WHERE user_id = %s",
        (combined, user_id),
    )


def append_symptom(user_id: int, symptom: str) -> None:
    if not symptom.strip():
        return
    context = get_or_create(user_id)
    symptoms = context.get("reported_symptoms") or []
    if isinstance(symptoms, str):
        symptoms = json.loads(symptoms)
    symptoms.append({"text": symptom.strip(), "at": datetime.now(timezone.utc).isoformat()})
    db.execute(
        "UPDATE whatsapp_patient_context SET reported_symptoms = %s, updated_at = now() WHERE user_id = %s",
        (json.dumps(symptoms, ensure_ascii=False), user_id),
    )


def set_self_care_plan(user_id: int, plan_text: str) -> None:
    get_or_create(user_id)
    db.execute(
        """
        UPDATE whatsapp_patient_context
        SET self_care_plan = %s, self_care_plan_issued_at = now(), updated_at = now()
        WHERE user_id = %s
        """,
        (plan_text, user_id),
    )


def mark_meal_checkin(user_id: int, response: Optional[str] = None) -> None:
    get_or_create(user_id)
    db.execute(
        """
        UPDATE whatsapp_patient_context
        SET last_meal_checkin_at = now(), last_meal_checkin_response = %s, updated_at = now()
        WHERE user_id = %s
        """,
        (response, user_id),
    )


def mark_wellness_checkin(user_id: int) -> None:
    get_or_create(user_id)
    db.execute(
        "UPDATE whatsapp_patient_context SET last_wellness_checkin_at = now(), updated_at = now() WHERE user_id = %s",
        (user_id,),
    )


def context_to_text(context: dict[str, Any]) -> str:
    """Renders a PatientContext row into the block the agent's system prompt
    is built from — the closest thing to `build_system_prompt` in the spec's
    pseudocode, kept as plain text rather than a template engine since every
    other agent in this codebase already composes its system prompt this way
    (see whatsapp_agent._system_prompt)."""
    lines: list[str] = []
    summary = context.get("conversation_summary") or ""
    lines.append(f"Conversation history summary:\n{summary or '(no prior conversation on file)'}")

    plan = context.get("self_care_plan")
    if plan:
        lines.append(f"Current self-care plan (issued {context.get('self_care_plan_issued_at')}):\n{plan}")
    else:
        lines.append("No self-care plan has been issued yet.")

    last_meal = context.get("last_meal_checkin_at")
    if last_meal:
        lines.append(
            f"Last meal check-in: {last_meal} — response: {context.get('last_meal_checkin_response') or '(no response recorded)'}"
        )
    else:
        lines.append("No meal check-in has been sent yet.")

    last_wellness = context.get("last_wellness_checkin_at")
    lines.append(f"Last wellness check-in: {last_wellness or '(never)'}")

    symptoms = context.get("reported_symptoms") or []
    if isinstance(symptoms, str):
        symptoms = json.loads(symptoms)
    if symptoms:
        lines.append("Symptoms the patient has previously mentioned:")
        for s in symptoms[-10:]:
            lines.append(f"  - {s.get('text')} (noted {s.get('at')})")
    else:
        lines.append("No symptoms recorded yet.")

    return "\n".join(lines)
