"""Inbound WhatsApp router — the real Meta webhook's brain (req 12, 13).

For an inbound message: match the sender's phone to a registered patient,
classify intent (an OpenRouter call), then either:
  - book an appointment — always through core/booking.py (Postgres, no LLM,
    can't be double-booked, can't have an invented time), or
  - answer a question about their report / biomarkers / doctor context /
    appointments — using ONLY facts pulled from Postgres for that patient,
    phrased by one OpenRouter call constrained to those facts; if that call
    fails, a deterministic template built directly from the same facts is
    used instead (never fabricated).

At most two OpenRouter calls per inbound message (intent classification +
answer phrasing) — both bounded, deterministic-input, single-shot calls; this
is a separate concern from the screening pipeline's "exactly one call" rule
(req 5), which is specifically about the organ-prediction decision.
"""
from __future__ import annotations

from typing import Any, Optional

from .. import db
from ..schemas import AppointmentReplyIntent, WhatsAppQAAnswer
from ..security import normalize_phone
from . import booking, reference_data, whatsapp_client
from .appointment_graph import keyword_intent
from .content_llm import LLMError, structured_json_call


def _find_user_by_phone(phone: str) -> Optional[dict[str, Any]]:
    return db.fetch_one(
        "SELECT id, email, name, phone FROM users WHERE phone = %s",
        (normalize_phone(phone),),
    )


def _classify_intent(message: str, lang: str = "en") -> str:
    try:
        out = structured_json_call(
            system=(
                "You classify a patient's inbound WhatsApp message to a health-screening clinic assistant. "
                "intent is one of: confirm (they want to book/confirm an appointment), decline (they say no "
                "to a booking), reschedule (they want a different appointment time), question (they're asking "
                "about their report, biomarker values, their doctor's notes, or their appointments), unknown."
            ),
            user=f"Patient message ({lang}): {message!r}",
            model_cls=AppointmentReplyIntent,
            max_tokens=200,
            temperature=0.0,
        )
        return out.intent
    except LLMError as exc:
        print(f"[whatsapp_agent.classify] fallback: {exc}")
        return keyword_intent(message)


def _gather_patient_facts(user: dict[str, Any]) -> dict[str, Any]:
    """Only real, retrieved data — nothing here is generated."""
    latest_row = reference_data.get_latest_row()
    reading = reference_data.row_to_reading(latest_row) if latest_row else None
    context = reference_data.get_context()
    upcoming = booking.list_upcoming_for_user(user["id"])
    latest_screening = db.fetch_one(
        """
        SELECT case_id, status, ai_prediction, ai_confidence, ai_reason
        FROM screening_cases
        WHERE status = 'COMPLETED'
        ORDER BY id DESC
        LIMIT 1
        """
    )
    return {
        "reading": reading,
        "context": context,
        "upcoming_appointments": upcoming,
        "latest_screening": latest_screening,
    }


def _facts_to_text(facts: dict[str, Any]) -> str:
    lines: list[str] = []
    reading = facts.get("reading")
    if reading:
        lines.append("Latest biomarker reading:")
        for key, m in reading["metrics"].items():
            lines.append(f"  - {key}: {m['value']}{m['unit']} (status: {m['status']})")
        lines.append(f"  Health areas: {reading['healthAreas']}")
    else:
        lines.append("No biomarker readings on file yet.")

    ctx = facts.get("context") or {}
    if ctx.get("diagnosis") or ctx.get("medications") or ctx.get("notes"):
        lines.append(
            f"Doctor context — diagnosis: {ctx.get('diagnosis') or '(none)'}; "
            f"medications: {ctx.get('medications') or '(none)'}; notes: {ctx.get('notes') or '(none)'}"
        )
    else:
        lines.append("No doctor context on file yet.")

    screening = facts.get("latest_screening")
    if screening:
        lines.append(
            f"Latest deep screening analysis (case {screening['case_id']}): predicted "
            f"{screening['ai_prediction']} ({round((screening['ai_confidence'] or 0) * 100)}% confidence) — "
            f"{screening['ai_reason']}"
        )
    else:
        lines.append("No deep screening analysis has been run yet.")

    upcoming = facts.get("upcoming_appointments") or []
    if upcoming:
        lines.append("Upcoming appointments:")
        for appt in upcoming:
            lines.append(f"  - {appt['when_human']} at {appt['clinic']}, {appt['branch']}")
    else:
        lines.append("No upcoming appointments booked.")

    return "\n".join(lines)


def _fallback_answer(facts: dict[str, Any], lang: str) -> str:
    """Deterministic answer built directly from the same facts — used only if
    the OpenRouter phrasing call fails. Never invents a value (req 8's spirit,
    applied here too)."""
    return _facts_to_text(facts) if lang != "ar" else (
        "إليك آخر ما لدينا من بيانات:\n" + _facts_to_text(facts)
    )


def _answer_question(message: str, facts: dict[str, Any], lang: str = "en") -> str:
    try:
        out = structured_json_call(
            system=(
                "You are NOVERA's WhatsApp assistant. Answer the patient's question using ONLY the facts "
                "supplied below — never invent a biomarker value, diagnosis, prediction, or appointment time "
                "that isn't in the facts. If the facts don't contain the answer, say so plainly and suggest "
                "checking the app. Keep the reply short (2-5 sentences), warm, and in "
                f"{'Arabic' if lang == 'ar' else 'English'}. This is screening support, not medical advice."
            ),
            user=f"Patient question: {message!r}\n\nKnown facts:\n{_facts_to_text(facts)}",
            model_cls=WhatsAppQAAnswer,
            max_tokens=500,
            temperature=0.2,
        )
        return out.reply
    except LLMError as exc:
        print(f"[whatsapp_agent.answer] fallback: {exc}")
        return _fallback_answer(facts, lang)


def handle_inbound(from_number: str, text: str, lang: str = "en") -> str:
    """Returns the reply text to send back via the Meta Graph API."""
    user = _find_user_by_phone(from_number)
    intent = _classify_intent(text, lang)

    if intent == "confirm":
        result = booking.find_and_book_slot(
            user_id=user["id"] if user else None,
            phone=normalize_phone(from_number),
            channel="whatsapp",
        )
        return whatsapp_client.confirmation_message(result)

    if intent == "decline":
        return (
            "No problem — I won't book anything. Message me any time and I'll set it up."
            if lang != "ar" else "لا مشكلة — لن أحجز شيئاً. راسلني في أي وقت وسأرتب الموعد."
        )

    if intent == "reschedule":
        from .. import config
        return (
            f"Sure — tell me a day and time that suits you and I'll rebook at {config.CLINIC_NAME}, {config.CLINIC_BRANCH}."
            if lang != "ar" else f"بالطبع — أخبرني باليوم والوقت المناسب وسأعيد الحجز في {config.CLINIC_NAME}، {config.CLINIC_BRANCH}."
        )

    if intent == "question":
        if not user:
            return (
                "I couldn't find an account linked to this number yet — sign up in the Novera app with this "
                "phone number and I'll be able to answer questions about your report and appointments."
                if lang != "ar" else
                "لم أجد حساباً مرتبطاً بهذا الرقم بعد — سجّل في تطبيق نوفيرا بهذا الرقم وسأتمكن من الإجابة عن أسئلتك."
            )
        facts = _gather_patient_facts(user)
        return _answer_question(text, facts, lang)

    return whatsapp_client.offer_message()
