"""Autonomous WhatsApp Agent — see novera-whatsapp-autonomous-agent-spec.md.

Two entry points, one shared brain:
  - handle_inbound(): reactive — a patient sent a message (whatsapp.inbound
    trigger). Always within the 24h window by definition (they just messaged).
  - handle_trigger(): proactive — woken by something that isn't a patient
    message (screening.completed, appointment.completed, mealtime.checkin,
    wellness.checkin). Requires a resolved, registered `user` (a phone number
    a real account is tied to) since there's no inbound message to resolve
    one from. Gated by the 24h window in code (whatsapp_context/whatsapp_
    templates), never left to the model's judgment (spec §5).

Being triggered does NOT mean it has to message the patient — restraint is
part of the design (spec §3.3): the model can call get_patient_facts, decide
nothing's actually needed, and reply with no tool calls at all. Proactive
runs treat "no final reply" as a legitimate "stayed quiet" outcome, not a
failure needing a fallback (unlike the reactive path, which must always
answer the patient with something).

Booking/cancelling/rescheduling always goes through core/booking.py
(Postgres, no LLM in the write path, can't be double-booked, can't have an
invented time); factual answers are grounded ONLY in get_patient_facts.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from .. import config, db, ws
from ..security import normalize_phone
from . import (
    booking,
    clinic,
    content_llm,
    reference_data,
    report_pdf,
    whatsapp_client,
    whatsapp_context,
    whatsapp_gating,
    whatsapp_templates,
)
from .device_control import arm_device_for_user

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 5

# The 4 proactive triggers, plus the 1 reactive one — kept as a closed set so
# a typo'd trigger name fails loudly instead of silently building a vague
# system prompt (see _trigger_description below).
PROACTIVE_TRIGGERS = ("screening.completed", "appointment.completed", "mealtime.checkin", "wellness.checkin")

# Diagram wiring (frontend/src/data/liveWorkflow.js, lane 2) — every
# broadcast payload here follows the exact same PII discipline
# guidance_agent.py already established: node/status/coarse-label only,
# never a phone number, patient name, or message content.
_TRIGGER_TO_NODE = {
    "screening.completed": "wa_trigger_screening",
    "appointment.completed": "wa_trigger_appointment",
    "mealtime.checkin": "wa_trigger_meal",
    "wellness.checkin": "wa_trigger_wellness",
    "whatsapp.inbound": "wa_trigger_message",
}
_TOOL_TO_NODE = {
    "get_patient_facts": "wa_tool_facts",
    "check_slot_availability": "wa_tool_facts",
    "book_appointment": "wa_tool_booking",
    "cancel_appointment": "wa_tool_booking",
    "reschedule_appointment": "wa_tool_booking",
    "send_report_pdf": "wa_tool_media",
    "send_voice_note": "wa_tool_media",
    "send_appointment_offer": "wa_tool_offer",
    "send_post_appointment_followup": "wa_tool_checkin",
    "send_meal_checkin": "wa_tool_checkin",
    "send_wellness_checkin": "wa_tool_checkin",
    "update_patient_context": "wa_tool_memory",
    "request_sensor_reading": "wa_tool_facts",
}


def _wa_emit(node: str, status: str, label: str) -> None:
    """Best-effort — see ws.broadcast_from_thread's own docstring for why
    this never raises. Called from worker threads throughout this file."""
    ws.broadcast_from_thread({
        "type": "step",
        "source": "whatsapp",
        "node": node,
        "status": status,
        "label": label,
    })


def _wa_run_end(label: str) -> None:
    ws.broadcast_from_thread({"type": "run_end", "source": "whatsapp", "label": label})


def _find_user_by_phone(phone: str) -> Optional[dict[str, Any]]:
    normalized = normalize_phone(phone)
    row = db.fetch_one(
        "SELECT id, email, name, phone FROM users WHERE phone = %s",
        (normalized,),
    )
    # Temporary diagnostic (2026-08-19) — the WhatsApp -> dashboard link
    # depends entirely on this exact string match, and it's the one part of
    # the whole pipeline with no other way to verify short of DB access.
    # Railway's own private deploy logs only (not the public /ws/pipeline
    # broadcast), so logging the normalized number here is fine.
    logger.info("whatsapp_agent: phone lookup normalized=%s matched_user_id=%s",
                normalized, row["id"] if row else None)
    return row


def _gather_patient_facts(user: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Only real, retrieved data — nothing here is generated. Multi-tenant
    (2026-08-19): every read below is scoped to this specific user_id — an
    unregistered/no-user case returns nothing at all rather than falling
    back to someone else's data."""
    if not user:
        return {"reading": None, "context": None, "upcoming_appointments": [], "latest_screening": None, "wa_context": None}
    latest_row = reference_data.get_latest_row(user["id"])
    reading = reference_data.row_to_reading(latest_row) if latest_row else None
    context = reference_data.get_context(user["id"])
    upcoming = booking.list_upcoming_for_user(user["id"])
    latest_screening = db.fetch_one(
        """
        SELECT case_id, status, ai_prediction, ai_confidence, ai_reason
        FROM screening_cases
        WHERE status = 'COMPLETED' AND user_id = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (user["id"],),
    )
    wa_context = whatsapp_context.get_or_create(user["id"])
    return {
        "reading": reading,
        "context": context,
        "upcoming_appointments": upcoming,
        "latest_screening": latest_screening,
        "wa_context": wa_context,
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

    wa_context = facts.get("wa_context")
    if wa_context:
        lines.append("WhatsApp conversation memory:")
        lines.append(whatsapp_context.context_to_text(wa_context))

    return "\n".join(lines)


def _fallback_answer(facts: dict[str, Any], lang: str) -> str:
    """Deterministic answer built directly from the same facts — used only if
    the agent loop fails to produce a final reply. Never invents a value.
    Only used on the reactive path (a proactive trigger's "no reply" is a
    legitimate quiet outcome, not something needing a fallback)."""
    return _facts_to_text(facts) if lang != "ar" else (
        "إليك آخر ما لدينا من بيانات:\n" + _facts_to_text(facts)
    )


def _unregistered_message(lang: str) -> str:
    return (
        f"I couldn't find an account linked to this number yet — sign up here with this same phone "
        f"number and message me again once you're done, I'll take it from there: {config.SIGNUP_URL}"
        if lang != "ar" else
        f"لم أجد حساباً مرتبطاً بهذا الرقم بعد — سجّل من هنا بنفس رقم الهاتف هذا ثم راسلني مرة أخرى "
        f"وسأكمل معك: {config.SIGNUP_URL}"
    )


# ---------------------------------------------------------------------------
# tools — built fresh per run, closing over that run's resolved
# user/phone/lang/context so concurrent runs never share state.
# ---------------------------------------------------------------------------
def _build_tools(user: Optional[dict[str, Any]], phone: str, lang: str, within_window: bool) -> list:
    facts_cache: dict[str, Any] = {}

    def _context() -> dict[str, Any]:
        return whatsapp_context.get_or_create(user["id"]) if user else {}

    @tool
    def get_patient_facts() -> str:
        """Look up this patient's real, on-file facts: latest biomarker reading,
        doctor context, latest deep screening analysis, upcoming appointments,
        and WhatsApp conversation memory (prior summary, self-care plan,
        check-in history, previously mentioned symptoms). Call this before
        answering any question, and before deciding whether a proactive
        trigger actually needs a message sent — never answer or act from
        memory or guesswork."""
        if not user:
            return (
                "No account is linked to this phone number, so no patient facts are "
                "available. Tell the patient to sign up with this same phone number, and "
                f"give them this exact link to do it: {config.SIGNUP_URL}"
            )
        if "facts" not in facts_cache:
            facts_cache["facts"] = _gather_patient_facts(user)
        return _facts_to_text(facts_cache["facts"])

    @tool
    def check_slot_availability() -> str:
        """Preview the next available appointment slot WITHOUT booking it."""
        slot, reason = clinic.first_candidate_slot()
        return f"Next available slot: {slot.strftime('%A, %d %b %Y at %I:%M %p')} ({reason})."

    @tool
    def book_appointment() -> str:
        """Book the next available appointment slot for this patient. REAL
        write to the database. Only call this once the patient has clearly
        agreed (e.g. said yes/confirm/book it), not just asked about
        availability. Always finds the next open slot itself; never promise
        or invent a specific time first."""
        result = booking.find_and_book_slot(user_id=user["id"] if user else None, phone=phone, channel="whatsapp")
        logger.info("whatsapp_agent book_appointment: phone=%s user_id=%s appointment_id=%s",
                    phone, user["id"] if user else None, result["id"])
        return whatsapp_client.confirmation_message(result)

    @tool
    def cancel_appointment() -> str:
        """Cancel this patient's next upcoming appointment. REAL write to the
        database. Only when the patient has clearly asked to cancel."""
        existing = booking.find_upcoming_booking_for_phone(phone)
        if not existing:
            return "This patient has no upcoming appointment to cancel."
        ok = booking.cancel_booking(existing["id"])
        if not ok:
            return "Could not cancel — the appointment may have already been cancelled."
        logger.info("whatsapp_agent cancel_appointment: phone=%s appointment_id=%s", phone, existing["id"])
        return whatsapp_client.cancellation_message(existing)

    @tool
    def reschedule_appointment() -> str:
        """Cancel this patient's next upcoming appointment and book the next
        available new slot in its place. REAL write. Only when the patient has
        clearly asked to move/change an existing appointment — always books
        the next available slot, cannot reserve a specific named time."""
        existing = booking.find_upcoming_booking_for_phone(phone)
        if not existing:
            return "This patient has no upcoming appointment to reschedule — use book_appointment instead."
        new_booking = booking.reschedule_booking(existing["id"], phone=phone, user_id=user["id"] if user else None)
        logger.info("whatsapp_agent reschedule_appointment: phone=%s old=%s new=%s",
                    phone, existing["id"], new_booking["id"])
        return whatsapp_client.reschedule_message(existing, new_booking)

    tools = [get_patient_facts, check_slot_availability, book_appointment, cancel_appointment, reschedule_appointment]

    # send_report_pdf and send_voice_note attach real media/documents — Meta
    # templates can't carry those, so unlike the 3 semantic proactive-send
    # tools below (which internally pick freeform vs. template), these two
    # are only offered to the model at all when the window is actually open.
    # On the reactive path within_window is always True (the patient just
    # messaged), so this never restricts today's normal Q&A behavior.
    if within_window:
        @tool
        def send_report_pdf() -> str:
            """Generate this patient's latest screening report as a PDF and
            send it as a WhatsApp document attachment. Only when the patient
            has clearly asked for their report as a PDF/document/file — not
            for a general question about their report, which get_patient_facts
            already answers in text."""
            if not user:
                return "No account is linked to this phone number, so there's no report to send."
            row = reference_data.get_latest_row(user["id"])
            if not row:
                return "This patient has no biomarker readings on file yet, so there's no report to generate."
            reading = reference_data.row_to_reading(row)
            ctx = reference_data.get_context(user["id"])
            report_data = content_llm.report_agent(reading, ctx, user["id"], lang="en")
            pdf_bytes = report_pdf.build_report_pdf(reading, report_data)
            result = whatsapp_client.send_document(
                pdf_bytes, filename="novera-screening-report.pdf",
                caption="Your NOVERA screening report.", to=phone,
            )
            logger.info("whatsapp_agent send_report_pdf: phone=%s delivered=%s", phone, result.get("delivered"))
            if result.get("delivered"):
                whatsapp_context.mark_outbound(user["id"])
                return "The report PDF was sent successfully as a WhatsApp document attachment in this conversation."
            return f"Sending the report PDF failed ({result.get('reason', 'unknown error')})."

        @tool
        def send_voice_note() -> str:
            """Generate a spoken-style screening summary and send it to the
            patient. NOTE — current limitation, be honest with the patient
            about it if asked directly: this sends the summary as a WRITTEN
            text message, not a real synthesized audio voice note — no
            text-to-speech audio pipeline is wired up on the backend yet.
            Don't tell the patient "here's your voice note" as if audio was
            attached; frame it as a written spoken-style summary."""
            if not user:
                return "No account is linked to this phone number, so there's no summary to send."
            row = reference_data.get_latest_row(user["id"])
            if not row:
                return "This patient has no biomarker readings on file yet."
            reading = reference_data.row_to_reading(row)
            voice_out = content_llm.voice_agent(reading, lang="en")
            script = voice_out.get("script", "")
            body = "🎙️ Spoken-style summary (text — audio isn't wired up yet):\n\n" + script
            result = whatsapp_client.send_message(body, to=phone)
            logger.info("whatsapp_agent send_voice_note: phone=%s delivered=%s", phone, result.get("delivered"))
            if result.get("delivered"):
                whatsapp_context.mark_outbound(user["id"])
                return "Sent as a written spoken-style summary (real audio synthesis isn't built yet)."
            return f"Sending the summary failed ({result.get('reason', 'unknown error')})."

        tools += [send_report_pdf, send_voice_note]

    @tool
    def send_appointment_offer(organ: str) -> str:
        """Offer the patient a real clinic appointment for a specific flagged
        organ system ('KIDNEY', 'STOMACH', or 'ORAL' — get this from
        get_patient_facts' latest screening result, never guess it). Sends a
        real message (free-form if the patient messaged in the last 24h,
        otherwise a pre-approved template automatically — you don't choose
        which, the code does). Use when a screening flagged medium/high and a
        follow-up seems warranted, or when the patient asks about booking
        without a specific date in mind."""
        if not user:
            return "No account is linked to this phone number, so no offer can be sent."
        facts = facts_cache.get("facts") or _gather_patient_facts(user)
        screening = facts.get("latest_screening")
        case_id = screening["case_id"] if screening else None
        result = whatsapp_templates.send_appointment_offer(
            context=_context(), to=phone, patient_name=user.get("name") or "there", organ=organ, case_id=case_id,
        )
        whatsapp_context.mark_outbound(user["id"])
        return f"Appointment offer sent (delivered={result.get('delivered')}, simulated={result.get('simulated')})."

    @tool
    def send_post_appointment_followup(organ: str) -> str:
        """Send a post-visit follow-up message asking how the appointment
        went and whether the patient has questions. Use for the
        appointment.completed trigger, or if the patient mentions they just
        had their appointment."""
        if not user:
            return "No account is linked to this phone number."
        result = whatsapp_templates.send_appointment_followup(
            context=_context(), to=phone, patient_name=user.get("name") or "there", organ=organ,
        )
        whatsapp_context.mark_outbound(user["id"])
        return f"Post-appointment follow-up sent (delivered={result.get('delivered')})."

    @tool
    def send_meal_checkin() -> str:
        """Send a check-in asking whether the patient followed today's
        self-care food guidance. Use for the mealtime.checkin trigger — check
        get_patient_facts first to see if they already checked in today or
        already answered this in conversation; don't send a redundant one."""
        if not user:
            return "No account is linked to this phone number."
        result = whatsapp_templates.send_meal_checkin(
            context=_context(), to=phone, patient_name=user.get("name") or "there",
        )
        whatsapp_context.mark_outbound(user["id"])
        whatsapp_context.mark_meal_checkin(user["id"])
        return f"Meal check-in sent (delivered={result.get('delivered')})."

    @tool
    def send_wellness_checkin() -> str:
        """Send a general how-are-you-feeling check-in. Use for the
        wellness.checkin trigger — check get_patient_facts first; if the
        patient already reported feeling fine recently in conversation,
        prefer staying quiet over sending a redundant check-in."""
        if not user:
            return "No account is linked to this phone number."
        result = whatsapp_templates.send_wellness_checkin(
            context=_context(), to=phone, patient_name=user.get("name") or "there",
        )
        whatsapp_context.mark_outbound(user["id"])
        whatsapp_context.mark_wellness_checkin(user["id"])
        return f"Wellness check-in sent (delivered={result.get('delivered')})."

    @tool
    def update_patient_context(conversation_note: str = "", symptom: str = "", self_care_plan: str = "") -> str:
        """Write back whatever was just learned into this patient's persistent
        memory, so future triggers/conversations inherit it instead of
        starting fresh. Call this at the end of most turns where you learned
        something concrete — a preference stated, a symptom mentioned, a plan
        issued — not for turns where nothing new was learned.
        `conversation_note`: a short factual note to remember (e.g. "patient
        said they started the potassium-reduced diet on Monday").
        `symptom`: a specific symptom the patient mentioned, if any.
        `self_care_plan`: the full text of a newly generated/updated self-care
        plan, if you just created or changed one this turn."""
        if not user:
            return "No account is linked to this phone number — nothing to write context for."
        if conversation_note:
            whatsapp_context.append_conversation_note(user["id"], conversation_note)
        if symptom:
            whatsapp_context.append_symptom(user["id"], symptom)
        if self_care_plan:
            whatsapp_context.set_self_care_plan(user["id"], self_care_plan)
        if not (conversation_note or symptom or self_care_plan):
            return "Nothing was provided to save."
        return "Patient context updated."

    @tool
    def request_sensor_reading() -> str:
        """Arm the shared NOVERA sensor device for THIS patient's next
        capture, and tell them to go use it now. Use this when
        get_patient_facts shows this registered patient has zero readings on
        file — especially right after they've just registered — or whenever
        they ask how to take a reading. There is only one physical device
        shared across patients, so the reading only counts as theirs if
        armed this way first; mention that in your reply (e.g. "go ahead and
        use the device now — it's shared, so I've reserved the next reading
        for your account")."""
        if not user:
            return "No account is linked to this phone number — they need to register first."
        arm_device_for_user(user["id"])
        return "Device armed for this patient — their next capture on the shared sensor will be linked to their account."

    tools += [
        send_appointment_offer,
        send_post_appointment_followup,
        send_meal_checkin,
        send_wellness_checkin,
        update_patient_context,
        request_sensor_reading,
    ]
    return tools


_TRIGGER_DESCRIPTION = {
    "screening.completed": (
        "A new saliva screening just completed for this patient. Check get_patient_facts for the "
        "result. If the flag is medium or high, you should very likely send an appointment offer "
        "(the code will force one anyway if you don't, per the safety guarantee — but use your own "
        "judgment on tone and whether to add anything else, like a written spoken-style summary). "
        "If the flag is low, a brief reassuring note is optional, not required — restraint is fine."
    ),
    "appointment.completed": (
        "This patient's booked appointment time has just passed. Consider sending a post-appointment "
        "follow-up asking how it went. Check get_patient_facts first — if they've already been in "
        "touch since the appointment, a redundant follow-up may not be needed."
    ),
    "mealtime.checkin": (
        "It's this patient's configured meal check-in window. Check get_patient_facts — if they don't "
        "have an active self-care plan, or already checked in today, staying quiet is the right call. "
        "Otherwise, a brief meal check-in is appropriate."
    ),
    "wellness.checkin": (
        "It's this patient's configured wellness check-in cadence. Check get_patient_facts first — if "
        "they've recently reported how they're feeling in conversation, a redundant check-in reads as "
        "noise, not care. Use your judgment."
    ),
}


def _system_prompt(user: Optional[dict[str, Any]], lang: str, trigger: str) -> str:
    lang_name = "Arabic" if lang == "ar" else "English"
    registered_note = (
        "This phone number is linked to a registered patient account."
        if user else
        "This phone number is NOT linked to any registered patient account, so there are no "
        "personal facts to retrieve for it — get_patient_facts will say so if called. Your reply "
        f"MUST include this exact signup link so they can register with this same phone number: "
        f"{config.SIGNUP_URL}"
    )
    if trigger == "whatsapp.inbound":
        wake_reason = "A patient just sent you a WhatsApp message — see the message below."
        restraint_note = (
            "This is a direct reply, so you must always say something back — never leave the patient "
            "unanswered."
        )
    else:
        wake_reason = _TRIGGER_DESCRIPTION.get(trigger, f"Triggered by: {trigger}.")
        restraint_note = (
            "IMPORTANT: being triggered does not mean you must message the patient. Check "
            "get_patient_facts, use your judgment, and if nothing genuinely needs saying right now, "
            "call no send tool at all and just reply with a short internal note explaining why you "
            "stayed quiet. An agent that sends something on every wake-up reads as spam, not care."
        )
    return (
        "You are NOVERA's autonomous WhatsApp Agent for a saliva-biosensor health-screening clinic. "
        f"{registered_note}\n\n"
        f"Why you're running right now: {wake_reason}\n\n"
        f"{restraint_note}\n\n"
        "You have tools to look up this patient's real facts, book/cancel/reschedule a REAL clinic "
        "appointment, send their report/a spoken-style summary, send proactive outreach messages "
        "(appointment offers, follow-ups, meal/wellness check-ins), arm the shared sensor device for "
        "their next reading, and write back what you learn into their persistent memory via "
        "update_patient_context. Every send/booking/device tool has an immediate real-world effect — "
        "only call one when it's actually warranted, not reflexively.\n\n"
        "Typical flow: call get_patient_facts first in almost every case, before deciding anything. If "
        "get_patient_facts shows this registered patient has zero readings on file (common right after "
        "they've just registered), call request_sensor_reading and tell them to go use the shared device "
        "now — don't just say 'no data yet' and stop there. If they want to book, call book_appointment "
        "directly (never invent a specific time first). If they want to cancel/reschedule, use those "
        "tools. If they're asking about their report, biomarkers, doctor's notes, or appointments, answer "
        "ONLY from get_patient_facts — never another patient's data, only ever this one's. If they "
        "specifically ask for their report as a PDF/document, use send_report_pdf. End most turns where "
        "you learned something concrete by calling update_patient_context.\n\n"
        "Never invent a biomarker value, diagnosis, prediction, appointment time, or fact that didn't "
        "come from a tool result. When a tool result is already a ready-made patient-facing message "
        "(book/cancel/reschedule_appointment, or get_patient_facts telling you no account is linked), "
        "use it as your reply practically verbatim — translate if needed but keep every concrete detail "
        "(dates, times, address, phone, map link) exactly as given.\n\n"
        f"Keep any message warm and concise (2-5 sentences unless relaying a booking's full details), "
        f"entirely in {lang_name}. This is screening support, not medical advice. Meta's WhatsApp API "
        "only allows free-form replies within 24 hours of the patient's last message — that window is "
        "enforced in code (proactive send tools automatically fall back to an approved template outside "
        "it), not by you, but don't tell the patient you can message them again anytime unprompted."
    )


def _run_agent_loop(messages: list, tools: list) -> tuple[Optional[str], bool]:
    """Shared loop for both entry points. Returns (final_text_or_None,
    hit_iteration_cap)."""
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

    for _ in range(MAX_ITERATIONS):
        response = llm.invoke(messages)
        messages.append(response)
        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            if isinstance(response.content, str) and response.content.strip():
                return response.content.strip(), False
            return None, False
        for call in tool_calls:
            name = call.get("name")
            args = call.get("args") or {}
            call_id = call.get("id") or name
            tool_obj = tool_map.get(name)
            wa_node = _TOOL_TO_NODE.get(name)
            if wa_node:
                _wa_emit(wa_node, "start", f"Calling {name}")
            if tool_obj is None:
                result_text = f"Unknown tool: {name}"
                if wa_node:
                    _wa_emit(wa_node, "error", f"Unknown tool: {name}")
            else:
                try:
                    result_text = tool_obj.invoke(args)
                    if wa_node:
                        _wa_emit(wa_node, "success", f"{name} done")
                except Exception as exc:
                    logger.exception("whatsapp_agent tool %r raised", name)
                    result_text = f"Tool {name} raised an unexpected error: {exc}"
                    if wa_node:
                        _wa_emit(wa_node, "error", f"{name} failed")
            messages.append(ToolMessage(content=str(result_text), tool_call_id=call_id))
    return None, True


def handle_inbound(from_number: str, text: str, lang: str = "en") -> str:
    """Reactive entry point: a patient sent a WhatsApp message. Always
    returns a reply string — never leaves the patient unanswered, even on
    total failure (degrades to _fallback_answer())."""
    user = _find_user_by_phone(from_number)
    phone = normalize_phone(from_number)

    if user:
        whatsapp_context.mark_inbound(user["id"])

    if not config.AI_ENABLED:
        logger.info("whatsapp_agent: AI not configured, using deterministic fallback for phone=%s", phone)
        return _fallback_answer(_gather_patient_facts(user), lang) if user else _unregistered_message(lang)

    tools = _build_tools(user, phone, lang, within_window=True)
    messages: list = [
        SystemMessage(content=_system_prompt(user, lang, trigger="whatsapp.inbound")),
        HumanMessage(content=f"Patient WhatsApp message: {text!r}"),
    ]
    _wa_emit("wa_trigger_message", "start", "Patient message received")
    _wa_emit("wa_agent", "start", "WhatsApp Agent deciding")
    reply: Optional[str] = None
    loop_failed = False
    try:
        reply, hit_cap = _run_agent_loop(messages, tools)
        if hit_cap:
            logger.info("whatsapp_agent: hit iteration cap without a final reply for phone=%s", phone)
    except Exception:
        logger.exception("whatsapp_agent: agent loop failed for phone=%s", phone)
        loop_failed = True

    if reply:
        if user:
            whatsapp_context.mark_outbound(user["id"])
        _wa_emit("wa_trigger_message", "success", "Patient message handled")
        _wa_emit("wa_agent", "success", "Replied to patient")
        _wa_run_end("WhatsApp Agent replied to an inbound message")
        return reply

    # No tool-produced reply (loop failed, hit the iteration cap, or the
    # model returned empty content) — degrade to the deterministic
    # fallback, but the patient still always gets an answer either way.
    _wa_emit("wa_trigger_message", "success", "Patient message handled (fallback reply)")
    _wa_emit("wa_agent", "error" if loop_failed else "success",
              "Reply generation failed" if loop_failed else "Replied with fallback facts")
    _wa_run_end("WhatsApp Agent run failed" if loop_failed else "WhatsApp Agent replied (fallback)")

    if not user:
        return _unregistered_message(lang)
    return _fallback_answer(_gather_patient_facts(user), lang)


def handle_trigger(trigger: str, user: dict[str, Any], payload: Optional[dict[str, Any]] = None, lang: str = "en") -> None:
    """Proactive entry point: woken by something other than a patient message
    (see PROACTIVE_TRIGGERS). Requires an already-resolved, registered `user`
    — proactive outreach only ever targets a real account with a phone
    number. Fires and forgets: no reply is returned to a caller, since
    there's no inbound request to reply to. The model may legitimately decide
    to send nothing — that's success, not failure, logged as such."""
    if trigger not in PROACTIVE_TRIGGERS:
        logger.error("whatsapp_agent.handle_trigger: unknown trigger %r", trigger)
        return
    phone = normalize_phone(user.get("phone") or "")
    if not phone:
        logger.info("whatsapp_agent.handle_trigger: user_id=%s has no phone on file, skipping trigger=%s",
                    user.get("id"), trigger)
        return

    # Safety floor (spec §6): forced, not suggested, runs before the model
    # gets a turn at all — every proactive trigger passes through this, not
    # just screening.completed, as a general net in case a medium/high flag
    # somehow wasn't already handled by its own trigger.
    try:
        forced = whatsapp_gating.enforce_outreach_guarantee(user)
        if forced:
            logger.info("whatsapp_agent.handle_trigger: safety-floor outreach forced for user_id=%s (trigger=%s)",
                        user["id"], trigger)
    except Exception:
        logger.exception("whatsapp_agent.handle_trigger: enforce_outreach_guarantee failed for user_id=%s", user["id"])

    if not config.AI_ENABLED:
        logger.info("whatsapp_agent.handle_trigger: AI not configured, skipping trigger=%s for user_id=%s",
                    trigger, user.get("id"))
        return

    context = whatsapp_context.get_or_create(user["id"])
    within_window = whatsapp_context.within_24h_window(context)
    tools = _build_tools(user, phone, lang, within_window=within_window)

    payload_line = f"\n\nTrigger payload: {payload}" if payload else ""
    messages: list = [
        SystemMessage(content=_system_prompt(user, lang, trigger=trigger)),
        HumanMessage(content=f"Trigger fired: {trigger}{payload_line}"),
    ]
    wa_trigger_node = _TRIGGER_TO_NODE[trigger]
    _wa_emit(wa_trigger_node, "start", f"{trigger} fired")
    _wa_emit("wa_agent", "start", "WhatsApp Agent deciding")
    try:
        reply, hit_cap = _run_agent_loop(messages, tools)
        if hit_cap:
            logger.info("whatsapp_agent.handle_trigger: hit iteration cap for trigger=%s user_id=%s",
                        trigger, user["id"])
        logger.info("whatsapp_agent.handle_trigger: trigger=%s user_id=%s completed, model note=%r",
                    trigger, user["id"], reply)
        _wa_emit(wa_trigger_node, "success", f"{trigger} handled")
        # Coarse, non-identifying label only — `reply` is the model's own
        # free-form note and may reference patient-specific details (already
        # logged server-side only, above); never put it on the public socket,
        # same discipline guidance_agent.py's _summarize() docstring explains.
        _wa_emit("wa_agent", "success", "Decided to act" if reply else "Stayed quiet — no message needed")
        _wa_run_end(f"WhatsApp Agent handled {trigger}")
    except Exception:
        logger.exception("whatsapp_agent.handle_trigger: agent loop failed for trigger=%s user_id=%s",
                          trigger, user["id"])
        _wa_emit(wa_trigger_node, "error", f"{trigger} failed")
        _wa_emit("wa_agent", "error", "Run failed")
        _wa_run_end(f"WhatsApp Agent run failed ({trigger})")
