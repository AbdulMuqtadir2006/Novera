"""Inbound WhatsApp router — the real Meta webhook's brain (req 12, 13).

For an inbound message: match the sender's phone to a registered patient,
then run a real tool-calling agent loop (`ChatOpenAI(...).bind_tools(...)`,
same loop shape as `guidance_agent.py`) — the model itself decides which of
{look up patient facts, preview a slot, book, cancel, reschedule} to call and
in what order, rather than being routed through a fixed set of intent
branches. Booking/cancelling/rescheduling always goes through core/booking.py
(Postgres, no LLM in the write path itself, can't be double-booked, can't
have an invented time); answering a question is grounded ONLY in facts pulled
from Postgres for that patient via the get_patient_facts tool.

Every inbound message costs at most MAX_ITERATIONS OpenRouter calls (bounded,
same spirit as the old "at most two calls" note — this replaces the fixed
2-call shape with a bounded loop instead, since the number of tool calls now
genuinely depends on what the patient asked). If the model, or OpenRouter
itself, never produces a plain-text final reply, this degrades to
`_fallback_answer()` — a deterministic template built directly from real
facts — so the patient is never left unanswered.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from .. import config, db
from ..security import normalize_phone
from . import booking, clinic, reference_data, whatsapp_client

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 5


def _find_user_by_phone(phone: str) -> Optional[dict[str, Any]]:
    return db.fetch_one(
        "SELECT id, email, name, phone FROM users WHERE phone = %s",
        (normalize_phone(phone),),
    )


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
    the agent loop fails to produce a final reply. Never invents a value (req
    8's spirit, applied here too)."""
    return _facts_to_text(facts) if lang != "ar" else (
        "إليك آخر ما لدينا من بيانات:\n" + _facts_to_text(facts)
    )


def _unregistered_message(lang: str) -> str:
    return (
        "I couldn't find an account linked to this number yet — sign up in the Novera app with this "
        "phone number and I'll be able to answer questions about your report and appointments."
        if lang != "ar" else
        "لم أجد حساباً مرتبطاً بهذا الرقم بعد — سجّل في تطبيق نوفيرا بهذا الرقم وسأتمكن من الإجابة عن أسئلتك."
    )


# ---------------------------------------------------------------------------
# tools — built fresh per inbound message, closing over that message's
# resolved user/phone/lang so concurrent requests never share state.
# ---------------------------------------------------------------------------
def _build_tools(user: Optional[dict[str, Any]], phone: str, lang: str) -> list:
    facts_cache: dict[str, Any] = {}

    @tool
    def get_patient_facts() -> str:
        """Look up this patient's real, on-file facts: latest biomarker reading,
        doctor context (diagnosis/medications/notes), latest deep screening
        analysis, and upcoming appointments. Call this before answering any
        question about the patient's report, biomarkers, doctor's notes, or
        appointments — never answer from memory or guesswork."""
        if not user:
            return (
                "No account is linked to this phone number, so no patient facts are "
                "available. Tell the patient to sign up in the Novera app with this "
                "phone number first."
            )
        if "facts" not in facts_cache:
            facts_cache["facts"] = _gather_patient_facts(user)
        return _facts_to_text(facts_cache["facts"])

    @tool
    def check_slot_availability() -> str:
        """Preview the next available appointment slot WITHOUT booking it — use
        this if the patient wants to know a time before committing, or if you
        want to describe a slot before they've confirmed they want it booked.
        Read-only, no database write."""
        slot, reason = clinic.first_candidate_slot()
        return f"Next available slot: {slot.strftime('%A, %d %b %Y at %I:%M %p')} ({reason})."

    @tool
    def book_appointment() -> str:
        """Book the next available appointment slot for this patient at the
        clinic. REAL write to the database. Only call this once the patient has
        clearly agreed to book (e.g. said yes/confirm/book it) — not just asked
        about availability. It always finds the next open slot itself; never
        promise or invent a specific time before calling it."""
        result = booking.find_and_book_slot(
            user_id=user["id"] if user else None,
            phone=phone,
            channel="whatsapp",
        )
        logger.info(
            "whatsapp_agent book_appointment: phone=%s user_id=%s appointment_id=%s slot=%s",
            phone, user["id"] if user else None, result["id"], result["when_iso"],
        )
        return whatsapp_client.confirmation_message(result)

    @tool
    def cancel_appointment() -> str:
        """Cancel this patient's next upcoming appointment. REAL write to the
        database. Only call this when the patient has clearly asked to cancel
        their own appointment."""
        existing = booking.find_upcoming_booking_for_phone(phone)
        if not existing:
            return "This patient has no upcoming appointment to cancel."
        ok = booking.cancel_booking(existing["id"])
        if not ok:
            return "Could not cancel — the appointment may have already been cancelled."
        logger.info(
            "whatsapp_agent cancel_appointment: phone=%s user_id=%s appointment_id=%s",
            phone, user["id"] if user else None, existing["id"],
        )
        return whatsapp_client.cancellation_message(existing)

    @tool
    def reschedule_appointment() -> str:
        """Cancel this patient's next upcoming appointment and book the next
        available new slot in its place. REAL write to the database. Only call
        this when the patient has clearly asked to move/change their existing
        appointment to a different time. This always books the next available
        slot — it cannot reserve a specific time the patient names, the same
        way book_appointment can't; if there's no existing appointment to move,
        it will say so — use book_appointment instead in that case."""
        existing = booking.find_upcoming_booking_for_phone(phone)
        if not existing:
            return (
                "This patient has no upcoming appointment to reschedule — if they "
                "want one booked, call book_appointment instead."
            )
        new_booking = booking.reschedule_booking(
            existing["id"], phone=phone, user_id=user["id"] if user else None
        )
        logger.info(
            "whatsapp_agent reschedule_appointment: phone=%s user_id=%s old_appointment_id=%s "
            "new_appointment_id=%s new_slot=%s",
            phone, user["id"] if user else None, existing["id"], new_booking["id"], new_booking["when_iso"],
        )
        return whatsapp_client.reschedule_message(existing, new_booking)

    return [
        get_patient_facts,
        check_slot_availability,
        book_appointment,
        cancel_appointment,
        reschedule_appointment,
    ]


def _system_prompt(user: Optional[dict[str, Any]], lang: str) -> str:
    lang_name = "Arabic" if lang == "ar" else "English"
    registered_note = (
        "This phone number is linked to a registered patient account."
        if user else
        "This phone number is NOT linked to any registered patient account, so there are no "
        "personal facts (report/biomarkers/doctor notes) to retrieve for it — get_patient_facts "
        "will say so if called. If they ask a question about their report, biomarkers, or doctor's "
        "notes, warmly tell them to sign up in the Novera app with this phone number first. This "
        "does NOT block booking, cancelling, or rescheduling an appointment by phone number alone "
        "— those tools work the same regardless of registration, same as today."
    )
    return (
        "You are NOVERA's WhatsApp assistant for a saliva-biosensor health-screening clinic. "
        f"{registered_note}\n\n"
        "You have tools to look up this patient's real facts and to book/cancel/reschedule a "
        "REAL clinic appointment for THIS patient (the one texting you) only. Every booking, "
        "cancel, or reschedule tool call has an immediate real-world effect, so only call one "
        "when the patient's intent is clearly that action, not merely a question about it.\n\n"
        "Typical flow: if they want to book, call book_appointment directly — it always finds "
        "the next available slot itself, never promise a specific time yourself first. If they "
        "want to cancel, call cancel_appointment. If they want to move/change an existing "
        "appointment, call reschedule_appointment (also always rebooks the next available slot, "
        "not a time they name). If they just want to know a time before deciding, use "
        "check_slot_availability (read-only). If they decline or say no to a booking, just "
        "acknowledge warmly and don't call any write tool. If they're asking about their report, "
        "biomarker values, doctor's notes, or their existing appointments, call get_patient_facts "
        "first and answer ONLY from what it returns.\n\n"
        "Never invent a biomarker value, diagnosis, prediction, or appointment time that didn't "
        "come from a tool result. When a tool result is already a ready-made patient-facing "
        "message (from book_appointment, cancel_appointment, reschedule_appointment, or "
        "get_patient_facts telling you no account is linked), use it as your reply practically "
        "verbatim — translate it if needed but keep every concrete detail (dates, times, address, "
        "phone number, map link) exactly as given, never altered.\n\n"
        f"Keep replies warm and concise (2-5 sentences, unless relaying a booking's full details), "
        f"entirely in {lang_name}. This is screening support, not medical advice. Note: Meta's "
        "WhatsApp API only allows free-form replies within 24 hours of the patient's last message "
        "to you — that window is enforced by Meta, not by you, but don't tell the patient you can "
        "message them again anytime unprompted."
    )


def handle_inbound(from_number: str, text: str, lang: str = "en") -> str:
    """Returns the reply text to send back via the Meta Graph API.

    Runs a real tool-calling agent loop (get_patient_facts /
    check_slot_availability / book_appointment / cancel_appointment /
    reschedule_appointment) — the model decides which tools to call and in
    what order, same manual invoke -> tool_calls -> ToolMessage -> invoke loop
    shape as guidance_agent.py, just synchronous (this function's caller,
    routers/whatsapp.py, calls it without awaiting). Never raises: every
    failure path (AI not configured, an OpenRouter/tool exception mid-loop, or
    the iteration cap with no final reply) degrades to _fallback_answer()'s
    deterministic, fact-grounded reply rather than leaving the patient
    unanswered.
    """
    user = _find_user_by_phone(from_number)
    phone = normalize_phone(from_number)

    if not config.AI_ENABLED:
        logger.info("whatsapp_agent: AI not configured, using deterministic fallback for phone=%s", phone)
        return _fallback_answer(_gather_patient_facts(user), lang) if user else _unregistered_message(lang)

    tools = _build_tools(user, phone, lang)
    tool_map = {t.name: t for t in tools}
    llm = ChatOpenAI(
        model=config.OPENROUTER_MODEL_CONTENT,
        api_key=config.OPENROUTER_API_KEY,
        base_url=config.OPENROUTER_BASE_URL,
        temperature=0.2,
        timeout=config.OPENROUTER_TIMEOUT_SECONDS,
        max_retries=1,
        default_headers={"HTTP-Referer": "http://localhost", "X-Title": "NOVERA WhatsApp Agent"},
    ).bind_tools(tools)

    messages: list = [
        SystemMessage(content=_system_prompt(user, lang)),
        HumanMessage(content=f"Patient WhatsApp message: {text!r}"),
    ]

    try:
        for _ in range(MAX_ITERATIONS):
            response = llm.invoke(messages)
            messages.append(response)
            tool_calls = getattr(response, "tool_calls", None) or []
            if not tool_calls:
                if isinstance(response.content, str) and response.content.strip():
                    return response.content.strip()
                break
            for call in tool_calls:
                name = call.get("name")
                args = call.get("args") or {}
                call_id = call.get("id") or name
                tool_obj = tool_map.get(name)
                if tool_obj is None:
                    result_text = f"Unknown tool: {name}"
                else:
                    try:
                        result_text = tool_obj.invoke(args)
                    except Exception as exc:
                        logger.exception("whatsapp_agent tool %r raised for phone=%s", name, phone)
                        result_text = f"Tool {name} raised an unexpected error: {exc}"
                messages.append(ToolMessage(content=str(result_text), tool_call_id=call_id))
        else:
            logger.info("whatsapp_agent: hit iteration cap without a final reply for phone=%s", phone)
    except Exception:
        logger.exception("whatsapp_agent: agent loop failed for phone=%s", phone)

    # No final plain-text reply (iteration cap, empty content, or an
    # exception mid-loop) — never leave the patient with no reply at all.
    if not user:
        return _unregistered_message(lang)
    return _fallback_answer(_gather_patient_facts(user), lang)
