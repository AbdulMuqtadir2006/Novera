"""Autonomous WhatsApp Agent — see novera-whatsapp-autonomous-agent-spec.md.

Two entry points, one shared brain:
  - handle_inbound(): reactive — a patient sent a message (whatsapp.inbound
    trigger). Always within the 24h window by definition (they just messaged).
  - handle_trigger(): proactive — woken by something that isn't a patient
    message (sensor.reading_received, reading.followup, appointment.completed,
    mealtime.checkin, wellness.checkin — see PROACTIVE_TRIGGERS below).
    Requires a resolved, registered `user` (a phone number a real account is
    tied to) since there's no inbound message to resolve one from, except
    sensor.reading_received itself (see handle_trigger's own docstring).
    Gated by the 24h window in code (whatsapp_context/whatsapp_templates),
    never left to the model's judgment (spec §5).

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
import re
import time
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
    demo_account,
    reasoning_stream,
    reference_data,
    report_pdf,
    scoring,
    screening_llm,
    tts,
    whatsapp_client,
    whatsapp_context,
    whatsapp_gating,
    whatsapp_templates,
)
from .device_control import arm_device_for_user, device_state

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 7  # bumped 5 -> 7 (2026-08-20, orchestrator merge): a full
# reading-to-followup run can now need run_screening_pipeline -> generate_report
# -> send_appointment_offer -> update_patient_context -> final reply, tighter
# against the old cap than any trigger needed before the merge.

# The 5 proactive triggers, plus the 1 reactive one — kept as a closed set so
# a typo'd trigger name fails loudly instead of silently building a vague
# system prompt (see _trigger_description below).
#
# "screening.completed" retired 2026-08-20 (orchestrator merge, see
# novera-whatsapp-autonomous-agent-spec.md's successor doc) — Guidance Agent
# used to run the screening pipeline separately and fire that event as a
# hand-off. Now WhatsApp Agent runs the pipeline itself (run_screening_pipeline
# tool, ported from guidance_agent.py) directly off "sensor.reading_received",
# so there's no separate hand-off: one continuous run, not two agents passing
# a baton. guidance_agent.py has been deleted.
#
# "reading.followup" added 2026-08-22 (Hassan's call) — a separate, later
# "how are you feeling" check-in fired alongside sensor.reading_received (not
# instead of it, and not a delayed version of it — see routers/readings.py's
# add_reading and _delayed_reading_followup). Screening tools are hard-excluded
# for it via _build_tools' allow_screening param, since claim_new_case_from_
# latest_reading has no dedup against sensor.reading_received's own run.
PROACTIVE_TRIGGERS = (
    "sensor.reading_received", "reading.followup", "appointment.completed", "mealtime.checkin", "wellness.checkin",
)

# In-flight/throttle guard for sensor.reading_received specifically — ported
# unchanged from guidance_agent.py's module-level _in_progress/
# _last_completed_at (2026-08-20 orchestrator merge). Global, not per-user,
# same as before: two different users' readings within 60s of each other
# still means the second one's autonomous run is skipped, not queued — an
# existing limitation, not something this merge changes. Only the
# sensor.reading_received path is gated by this; the other 4 triggers were
# never covered by it and still aren't.
READING_THROTTLE_SECONDS = 60
_reading_run_in_progress = False
_reading_run_last_completed_at: Optional[float] = None


def _try_acquire_reading_run() -> bool:
    global _reading_run_in_progress, _reading_run_last_completed_at
    if _reading_run_in_progress:
        return False
    now = time.monotonic()
    if _reading_run_last_completed_at is not None and (now - _reading_run_last_completed_at) < READING_THROTTLE_SECONDS:
        return False
    _reading_run_in_progress = True
    return True


def _release_reading_run() -> None:
    global _reading_run_in_progress, _reading_run_last_completed_at
    _reading_run_in_progress = False
    _reading_run_last_completed_at = time.monotonic()

# Diagram wiring (frontend/src/data/liveWorkflow.js, lane 2) — every
# broadcast payload here follows the exact same PII discipline
# guidance_agent.py already established: node/status/coarse-label only,
# never a phone number, patient name, or message content.
_TRIGGER_TO_NODE = {
    "sensor.reading_received": "wa_trigger_reading",
    # Reuses the wellness node (semantically the closest — a "how are you
    # feeling" style outreach) rather than inventing a new diagram node the
    # frontend doesn't know how to draw.
    "reading.followup": "wa_trigger_wellness",
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
    # Bundled into the same diagram node as report/voice (2026-08-23) — the
    # live workflow diagram's "Report & Voice" node/hover-detail text
    # doesn't yet mention self-care specifically; a frontend-copy follow-up,
    # not required for this tool to work.
    "send_self_care_plan": "wa_tool_media",
    "send_appointment_offer": "wa_tool_offer",
    "send_post_appointment_followup": "wa_tool_checkin",
    "send_meal_checkin": "wa_tool_checkin",
    "send_wellness_checkin": "wa_tool_checkin",
    "update_patient_context": "wa_tool_memory",
    "request_sensor_reading": "wa_tool_facts",
    # generate_report/request_retest ported from guidance_agent.py (2026-08-20
    # orchestrator merge) — the generic per-tool broadcast below is enough for
    # these two, same as every other tool here. run_screening_pipeline is
    # deliberately NOT mapped — it broadcasts its own internal sub-steps
    # (validate/score_kidney/score_liver/score_oral) directly, since one
    # coarse start/success pair wouldn't show the real work happening inside it.
    "generate_report": "wa_tool_report",
    "request_retest": "wa_tool_retest",
}

# Bug fix (found 2026-08-23, user-reported "messages sometimes sent 2 times"):
# these 7 tools each send a REAL WhatsApp message directly (whatsapp_client.
# send_message/send_document) as their own side effect, then return a status
# string describing what they just did. The system prompt tells the model to
# relay a tool's "ready-made patient-facing message" back practically
# verbatim as its own final reply — correct and necessary for book/cancel/
# reschedule_appointment (which only ever return a string, never send
# anything themselves), but for these 7, the model doing the same thing
# produces a genuine SECOND real send of a redundant restatement. See
# _run_agent_loop's self_send_fired tracking and handle_inbound's use of it.
_SELF_SENDING_TOOL_NAMES = frozenset({
    "send_report_pdf",
    "send_voice_note",
    "send_self_care_plan",
    "send_appointment_offer",
    "send_post_appointment_followup",
    "send_meal_checkin",
    "send_wellness_checkin",
})


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


# Admin/demo WhatsApp sessions (2026-08-23, Hassan's call) — in-process
# only, same accepted-limitation pattern as _reading_run_in_progress/
# _delayed_reading_followup elsewhere in this codebase: an app restart
# silently drops any active session, and a multi-worker deployment wouldn't
# share this across processes. Fine for a prototype tested by one person;
# not something to build a real session store for.
ADMIN_SESSION_TTL_SECONDS = 24 * 3600
_admin_authenticated_at: dict[str, float] = {}  # normalized phone -> time.monotonic()

# Defense-in-depth against brute-forcing ADMIN_WA_TRIGGER_PHRASE (2026-08-25)
# — not real security (the phrase itself is the actual protection, per its
# own config.py docstring), just a cheap guard against automated guessing
# in front of a live demo audience. Only counts short, phrase-length-ish
# non-matching messages as a "guess", not every message a patient happens to
# send — an ordinary conversation, even a chatty one, is very unlikely to
# trip this; a script trying many candidate phrases rapidly will.
ADMIN_TRIGGER_MAX_ATTEMPTS = 8
ADMIN_TRIGGER_WINDOW_SECONDS = 10 * 60
_admin_trigger_attempts: dict[str, list[float]] = {}  # normalized phone -> guess timestamps


def _admin_trigger_locked_out(phone: str) -> bool:
    now = time.monotonic()
    attempts = [t for t in _admin_trigger_attempts.get(phone, []) if now - t <= ADMIN_TRIGGER_WINDOW_SECONDS]
    _admin_trigger_attempts[phone] = attempts
    return len(attempts) >= ADMIN_TRIGGER_MAX_ATTEMPTS


def _record_admin_trigger_attempt(phone: str) -> None:
    _admin_trigger_attempts.setdefault(phone, []).append(time.monotonic())


def _admin_session_user() -> Optional[dict[str, Any]]:
    admin_id = demo_account.admin_user_id()
    if not admin_id:
        return None
    return db.fetch_one("SELECT id, email, name, phone FROM users WHERE id = %s", (admin_id,))


def _admin_session_active(phone: str) -> bool:
    ts = _admin_authenticated_at.get(phone)
    if ts is None:
        return False
    if time.monotonic() - ts > ADMIN_SESSION_TTL_SECONDS:
        del _admin_authenticated_at[phone]
        return False
    return True


def _try_admin_trigger(from_number: str, text: str) -> Optional[dict[str, Any]]:
    """Admin/demo access (2026-08-23, Hassan's call) — see config.ADMIN_WA_
    TRIGGER_PHRASE's own docstring for the security tradeoff this makes
    (a shared-secret phrase, not phone-bound, by explicit choice so it works
    from any device for demos). Requires the message text to be EXACTLY the
    configured phrase (case/whitespace-insensitive) — not a substring match,
    so a patient's real message can't accidentally trigger it. On match,
    remembers this phone as admin-authenticated for ADMIN_SESSION_TTL_
    SECONDS (see _admin_session_active) so the sender doesn't have to resend
    the phrase every message. Returns the admin user row on match, None
    otherwise (including when the feature is unconfigured, the admin account
    hasn't been created yet, or the sender is currently rate-limited — see
    _admin_trigger_locked_out)."""
    phrase = config.ADMIN_WA_TRIGGER_PHRASE
    if not phrase or not text:
        return None
    normalized = normalize_phone(from_number)
    stripped = text.strip()
    matches = stripped.casefold() == phrase.strip().casefold()
    if not matches:
        # Only a short, phrase-length-ish miss counts toward the guess
        # budget — a genuine conversational sentence from a patient
        # shouldn't burn down the same budget a real guessing script would.
        if len(stripped) <= len(phrase) + 20 and not _admin_trigger_locked_out(normalized):
            _record_admin_trigger_attempt(normalized)
        return None
    if _admin_trigger_locked_out(normalized):
        logger.warning("whatsapp_agent: admin trigger phrase matched but sender=%s is rate-limited, rejecting", normalized)
        return None
    row = _admin_session_user()
    if row:
        _admin_authenticated_at[normalized] = time.monotonic()
        # Server-side logs only (Railway's private deploy logs, same
        # discipline as _find_user_by_phone's own diagnostic above) — the
        # trigger phrase itself is never logged, only that it fired and
        # which sender number used it, for an audit trail.
        logger.info("whatsapp_agent: admin trigger recognized, sender=%s", normalized)
    return row


def _admin_intro_message(lang: str) -> str:
    """The admin/demo feature list — extracted (2026-08-23) so both the
    `madaar` trigger itself and _greeting_reply (a plain "hi" while an
    admin session is already active) send the exact same message. Every
    bullet is a real tool actually offered on this path (_build_tools with
    a registered user + phone + within_window=True + allow_screening
    default True) — keep this list in sync if a tool is added/removed
    there."""
    return (
        "🔑 Admin/demo mode is ON for this number for the next 24h — you're testing the full "
        "NOVERA experience as the demo account, no real sensor reading needed. You can ask me to:\n\n"
        "• Run the screening pipeline / generate a report from the latest (synthetic) reading\n"
        "• Send the report as a PDF\n"
        "• Send a spoken voice-note summary\n"
        "• Send the natural-recovery / self-care plan\n"
        "• Tell you what a doctor has noted (patient context memory)\n"
        "• Check slot availability, book / cancel / reschedule an appointment\n"
        "• Request a retest\n"
        "• Arm the shared sensor for a next capture\n\n"
        "⚠️ Caution: any appointment you book here is a REAL booking placed in the clinic's real "
        "system on the demo account — it is not simulated. In real (non-admin) operation, an "
        "appointment is only ever booked automatically when a real NOVERA Product sensor reading "
        "actually flags a concern — not on request like this. If you book one here just to test the "
        "flow, remember to cancel it afterward so it doesn't sit as a real slot."
        if lang != "ar" else
        "🔑 تم تفعيل وضع الإدارة/التجربة لهذا الرقم لمدة 24 ساعة — أنت تختبر تجربة نوفيرا الكاملة "
        "كحساب تجريبي، دون الحاجة لقراءة حقيقية من المستشعر. يمكنك أن تطلب مني:\n\n"
        "• تشغيل مسار الفحص / إنشاء تقرير من آخر قراءة (تجريبية)\n"
        "• إرسال التقرير كملف PDF\n"
        "• إرسال ملخص صوتي منطوق\n"
        "• إرسال خطة التعافي الطبيعي / العناية الذاتية\n"
        "• إخبارك بما سجّله الطبيب (ذاكرة سياق المريض)\n"
        "• التحقق من توفر المواعيد، أو حجز/إلغاء/إعادة جدولة موعد\n"
        "• طلب إعادة الفحص\n"
        "• تجهيز المستشعر المشترك لقراءة قادمة\n\n"
        "⚠️ تنبيه: أي موعد تحجزه هنا هو حجز حقيقي فعلاً في نظام العيادة الحقيقي على الحساب التجريبي "
        "— وليس محاكاة. في التشغيل الفعلي (غير الإداري)، لا يُحجز الموعد تلقائيًا إلا عندما ترصد "
        "قراءة حقيقية من منتج نوفيرا مشكلة فعلية — وليس بمجرد الطلب كما هنا. إذا حجزت موعدًا هنا "
        "لتجربة المسار فقط، تذكّر إلغاءه لاحقًا حتى لا يبقى كموعد حقيقي."
    )


# Matches a bare greeting and nothing else — "hi", "hey", "hello novera",
# "hi there!", etc. — NOT a real question that happens to start with one
# (e.g. "hi, is my report ready?"), which needs the real agent loop instead.
_GREETING_RE = re.compile(
    r"^(hi+|hey+|hello+|yo+|howdy|salam|assalamualaikum|marhaba|مرحبا|اهلا|أهلا|السلام عليكم)"
    r"\s*(novera|there)?\s*[!.,؟?]*$",
    re.IGNORECASE,
)


def _is_plain_greeting(text: str) -> bool:
    return bool(_GREETING_RE.match((text or "").strip()))


# Emergency-message keyword gate (2026-08-25) — deliberately simple and
# deterministic, not another LLM call: if something matters this much, don't
# trust it to a model call that could fail, drift, or get talked out of
# redirecting. Matches ANYWHERE in the message (unlike _GREETING_RE, which
# must match the whole message) since a real emergency is rarely phrased as
# a bare keyword. Kept to high-specificity phrases only (no bare "pain") so
# an ordinary question ("is mild stomach pain normal after eating?") never
# gets hijacked into the emergency reply.
_EMERGENCY_RE = re.compile(
    r"(can'?t breathe|cannot breathe|chest pain|heart attack|having a stroke|"
    r"severe bleeding|bleeding heavily|suicidal|kill myself|want to die|"
    r"overdose|need an ambulance|"
    r"لا أستطيع التنفس|ألم في الصدر|نوبة قلبية|سكتة دماغية|نزيف حاد|"
    r"أريد أن أموت|أفكر في الانتحار|أحتاج إسعاف)",
    re.IGNORECASE,
)


def _is_emergency_message(text: str) -> bool:
    return bool(_EMERGENCY_RE.search((text or "").strip()))


def _emergency_reply(lang: str) -> str:
    if lang == "ar":
        return (
            "🚨 نوفيرا أداة فحص أولي وليست خدمة طوارئ. إذا كانت هذه حالة طارئة حقيقية، يرجى "
            "الاتصال فورًا بالرقم 9999 (الطوارئ في عُمان) أو التوجه إلى أقرب قسم طوارئ الآن."
        )
    return (
        "🚨 NOVERA is a screening tool, not an emergency service. If this is a real medical "
        "emergency, please call 9999 (Oman's emergency number) or go to the nearest ER right now."
    )


def _greeting_reply(user: Optional[dict[str, Any]], lang: str) -> str:
    """A bare "hi/hey/hello" gets an instant, static feature-list reply
    instead of spending a full LLM round-trip on a message with nothing to
    actually decide (2026-08-23, Hassan's call — same request that asked
    the admin trigger get its own feature list). Reuses that exact admin
    message when the resolved account is the admin/demo one."""
    if user and demo_account.is_admin_account(user["id"]):
        return _admin_intro_message(lang)
    if not user:
        return (
            "👋 Hi! I'm NOVERA's WhatsApp Agent for saliva-biosensor health screening. This number "
            "isn't linked to an account yet — sign up here with this same phone number, then message "
            "me again and I can:\n\n"
            "• Show your latest biomarker reading & report\n"
            "• Send your report as a PDF or a spoken voice note\n"
            "• Send your natural-recovery / self-care plan\n"
            "• Tell you what your doctor has noted\n"
            "• Book, cancel, or reschedule an appointment\n"
            "• Arm the shared sensor for your next reading\n\n"
            f"Sign up here: {config.SIGNUP_URL}"
            if lang != "ar" else
            "👋 مرحباً! أنا وكيل واتساب نوفيرا لفحص الصحة عبر مستشعر اللعاب. هذا الرقم غير مرتبط بحساب "
            "بعد — سجّل من هنا بنفس رقم الهاتف هذا ثم راسلني مرة أخرى، وسأتمكن من:\n\n"
            "• عرض آخر قراءة للمؤشرات الحيوية والتقرير\n"
            "• إرسال تقريرك كملف PDF أو ملخص صوتي منطوق\n"
            "• إرسال خطة التعافي الطبيعي / العناية الذاتية\n"
            "• إخبارك بما سجّله الطبيب\n"
            "• حجز أو إلغاء أو إعادة جدولة موعد\n"
            "• تجهيز المستشعر المشترك لقراءتك القادمة\n\n"
            f"سجّل من هنا: {config.SIGNUP_URL}"
        )
    name_bit = f", {user['name']}" if user.get("name") else ""
    name_bit_ar = f"، {user['name']}" if user.get("name") else ""
    return (
        f"👋 Hi{name_bit}! I'm your NOVERA WhatsApp Agent. Message me any time to:\n\n"
        "• Check your latest biomarker reading & report\n"
        "• Get your report as a PDF or a spoken voice note\n"
        "• Get your natural-recovery / self-care plan\n"
        "• See what your doctor has noted\n"
        "• Book, cancel, or reschedule an appointment\n"
        "• Request a retest\n"
        "• Arm the sensor for your next reading\n\n"
        "⚠️ Note: booking, cancelling, or rescheduling here creates/changes a REAL appointment at "
        "the clinic — it's not a preview or a draft.\n\n"
        "Just tell me what you'd like."
        if lang != "ar" else
        f"👋 مرحباً{name_bit_ar}! أنا وكيل واتساب نوفيرا. راسلني في أي وقت من أجل:\n\n"
        "• التحقق من آخر قراءة للمؤشرات الحيوية والتقرير\n"
        "• الحصول على تقريرك كملف PDF أو ملخص صوتي منطوق\n"
        "• الحصول على خطة التعافي الطبيعي / العناية الذاتية\n"
        "• معرفة ما سجّله الطبيب\n"
        "• حجز أو إلغاء أو إعادة جدولة موعد\n"
        "• طلب إعادة الفحص\n"
        "• تجهيز المستشعر لقراءتك القادمة\n\n"
        "⚠️ ملاحظة: الحجز أو الإلغاء أو إعادة الجدولة هنا ينشئ أو يغيّر موعدًا حقيقيًا في العيادة — "
        "وليس معاينة أو مسودة.\n\n"
        "فقط أخبرني بما تريد."
    )


def _admin_booking_caution(user: Optional[dict[str, Any]], lang: str) -> str:
    """Appended (2026-08-23, Hassan's report) to book_appointment/
    reschedule_appointment's returned text — but only for the admin/demo
    account, whose bookings are otherwise indistinguishable from a real
    patient's in the confirmation message. Empty string for every real
    patient, so this changes nothing about their booking flow."""
    if not user or not demo_account.is_admin_account(user["id"]):
        return ""
    return (
        "\n\n⚠️ Demo booking made — this is a REAL slot in the clinic's real system on the demo "
        "account, not a simulation. In real (non-admin) operation, NOVERA never books an "
        "appointment just because it was asked; it only books automatically when a real NOVERA "
        "Product sensor reading actually flags a concern. Cancel this if it was just a test."
        if lang != "ar" else
        "\n\n⚠️ تم إجراء حجز تجريبي — هذا موعد حقيقي فعلاً في نظام العيادة على الحساب التجريبي، وليس "
        "محاكاة. في التشغيل الفعلي (غير الإداري)، لا تحجز نوفيرا موعدًا لمجرد الطلب؛ بل تحجزه تلقائيًا "
        "فقط عندما ترصد قراءة حقيقية من منتج نوفيرا مشكلة فعلية. ألغِ هذا الموعد إذا كان تجربة فقط."
    )


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


def _format_self_care_plan_for_whatsapp(plan: dict[str, Any], lang: str) -> str:
    """Renders a SelfCareOut-shaped dict (content_llm.self_care_agent's
    return shape — focusTitle/focusBody/dietPlan/areaTips) as readable
    WhatsApp text (2026-08-23, the send_self_care_plan tool). Deliberately
    skips the `nutrition` macro breakdown (calories/protein/carbs/fat per
    meal) — that's dense tabular detail suited to the website's Natural
    Recovery page, not a WhatsApp message; the diet plan + area tips are the
    part a patient actually wants to read on their phone."""
    diet = plan.get("dietPlan") or {}
    lines = [f"🌿 *{plan.get('focusTitle', 'Your natural recovery focus')}*", plan.get("focusBody", "").strip()]
    diet_label = "الوجبات" if lang == "ar" else "Diet plan"
    lines += ["", f"*{diet_label}:*"]
    meal_labels = (
        {"breakfast": "الفطور", "lunch": "الغداء", "dinner": "العشاء", "snacks": "وجبات خفيفة", "hydration": "السوائل"}
        if lang == "ar"
        else {"breakfast": "Breakfast", "lunch": "Lunch", "dinner": "Dinner", "snacks": "Snacks", "hydration": "Hydration"}
    )
    for key in ("breakfast", "lunch", "dinner", "snacks", "hydration"):
        if diet.get(key):
            lines.append(f"• {meal_labels[key]}: {diet[key]}")
    area_tips = plan.get("areaTips") or []
    if area_tips:
        tips_label = "نصائح حسب المجال:" if lang == "ar" else "Area tips:"
        lines += ["", f"*{tips_label}*"]
        for tip in area_tips:
            if tip.get("tip"):
                lines.append(f"• {tip.get('name', tip.get('id', ''))}: {tip['tip']}")
    return "\n".join(line for line in lines if line is not None)


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
def _build_tools(
    user: Optional[dict[str, Any]],
    phone: str,
    lang: str,
    within_window: bool,
    screening_state: Optional[dict[str, Any]] = None,
    allow_screening: bool = True,
    allow_booking: bool = True,
) -> list:
    facts_cache: dict[str, Any] = {}
    # Shared across run_screening_pipeline/generate_report/request_retest for
    # this one run only (fresh dict per _build_tools call, same "concurrent
    # runs never share state" guarantee facts_cache already has). Ported from
    # guidance_agent.py's _RunState (2026-08-20 orchestrator merge). Callers
    # that need to read the outcome after the loop (handle_trigger, for the
    # reasoning-stream narration and the post-screening safety-floor check)
    # pass their own dict in; handle_inbound doesn't need to, so it's created
    # here when omitted.
    if screening_state is None:
        screening_state = {}
    has_phone = bool(phone)

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
        return whatsapp_client.confirmation_message(result) + _admin_booking_caution(user, lang)

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
        return whatsapp_client.reschedule_message(existing, new_booking) + _admin_booking_caution(user, lang)

    # get_patient_facts/update_patient_context/request_sensor_reading and the
    # screening tools below never need a phone. Everything that messages or
    # books needs somewhere to send to — offering them without a phone would
    # just error when called, so they're excluded up front instead. This is
    # what lets sensor.reading_received run for accounts with no phone on
    # file (2026-08-20 orchestrator merge) without silently failing mid-tool.
    tools = [get_patient_facts]
    if has_phone:
        tools.append(check_slot_availability)
        # book/cancel/reschedule are REAL writes — only offered on the reactive
        # (patient-initiated) path (2026-08-25). Previously available on every
        # proactive/autonomous trigger too, restrained only by a prompt
        # sentence ("only call once the patient has agreed") — nothing
        # code-level stopped an autonomous run (e.g. wellness.checkin) from
        # booking/cancelling a real clinic slot on its own judgment. See
        # handle_trigger, which now always passes allow_booking=False.
        if allow_booking:
            tools += [book_appointment, cancel_appointment, reschedule_appointment]

    # send_report_pdf and send_voice_note attach real media/documents — Meta
    # templates can't carry those, so unlike the 3 semantic proactive-send
    # tools below (which internally pick freeform vs. template), these two
    # are only offered to the model at all when the window is actually open.
    # On the reactive path within_window is always True (the patient just
    # messaged), so this never restricts today's normal Q&A behavior.
    if within_window and has_phone:
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
            """Generate a spoken-style screening summary, synthesize it as
            real speech audio, and send it to the patient as a WhatsApp
            voice note. Only call when the patient has clearly asked for a
            voice note/audio/spoken summary."""
            if not user:
                return "No account is linked to this phone number, so there's no summary to send."
            row = reference_data.get_latest_row(user["id"])
            if not row:
                return "This patient has no biomarker readings on file yet."
            reading = reference_data.row_to_reading(row)
            voice_out = content_llm.voice_agent(reading, lang=lang)
            script = voice_out.get("script", "")
            try:
                audio_bytes = tts.synthesize(script, lang=lang)
            except tts.TTSError as exc:
                # Degrade to text rather than leave the patient with nothing
                # (2026-08-23: gTTS is an unofficial endpoint with no uptime
                # guarantee — see tts.py's own comment).
                logger.warning("whatsapp_agent send_voice_note: TTS failed, falling back to text: %s", exc)
                body = "🎙️ Spoken-style summary (voice synthesis is temporarily unavailable):\n\n" + script
                result = whatsapp_client.send_message(body, to=phone)
                if result.get("delivered"):
                    whatsapp_context.mark_outbound(user["id"])
                    return "Voice synthesis failed, so this was sent as a written spoken-style summary instead."
                return f"Sending the summary failed ({result.get('reason', 'unknown error')})."
            result = whatsapp_client.send_audio(audio_bytes, filename="novera-voice-summary.mp3", to=phone)
            logger.info("whatsapp_agent send_voice_note: phone=%s delivered=%s", phone, result.get("delivered"))
            if result.get("delivered"):
                whatsapp_context.mark_outbound(user["id"])
                return "A real synthesized-audio voice note was sent successfully as a WhatsApp audio attachment."
            return f"Sending the voice note failed ({result.get('reason', 'unknown error')})."

        @tool
        def send_self_care_plan() -> str:
            """Generate (or reuse the already-persisted) natural-recovery /
            self-care plan — what to eat and what to do to recover naturally
            — and send it as a WhatsApp message. Same content the website's
            Natural Recovery page shows, formatted as readable text. Only
            call when the patient has clearly asked what to eat/do to
            recover, or asked for their diet/self-care plan."""
            if not user:
                return "No account is linked to this phone number, so there's no plan to generate."
            plan = reference_data.get_self_care_plan(user["id"])
            if not plan:
                row = reference_data.get_latest_row(user["id"])
                if not row:
                    return "This patient has no biomarker readings on file yet, so there's no plan to generate."
                reading = reference_data.row_to_reading(row)
                ctx = reference_data.get_context(user["id"])
                history = reference_data.get_chat_history(user["id"])
                plan = content_llm.self_care_agent(reading, ctx, history, user["id"], lang)
            body = _format_self_care_plan_for_whatsapp(plan, lang)
            result = whatsapp_client.send_message(body, to=phone)
            logger.info("whatsapp_agent send_self_care_plan: phone=%s delivered=%s", phone, result.get("delivered"))
            if result.get("delivered"):
                whatsapp_context.mark_outbound(user["id"])
                return "Natural-recovery / self-care plan sent as a WhatsApp message."
            return f"Sending the plan failed ({result.get('reason', 'unknown error')})."

        tools += [send_report_pdf, send_voice_note, send_self_care_plan]

    @tool
    def send_appointment_offer(organ: str) -> str:
        """Offer the patient a real clinic appointment for a specific flagged
        organ system ('KIDNEY', 'LIVER', or 'ORAL' — get this from
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
        for your account"). If this returns saying the device is offline,
        tell the patient plainly that the sensor isn't connected right now
        and a new reading can't be taken until it is — don't imply it's
        armed anyway."""
        if not user:
            return "No account is linked to this phone number — they need to register first."
        # Bug fix (2026-08-23, Hassan's report): this used to arm the device
        # unconditionally even when it was offline, so the patient was told
        # "go ahead and use the device" for hardware that wasn't actually
        # there. Admin/demo account is explicitly exempt — it's meant to
        # work with no real sensor connected at all.
        if not demo_account.is_admin_account(user["id"]) and not device_state()["online"]:
            return (
                "The shared NOVERA sensor device is currently offline (no heartbeat), so it "
                "can NOT be armed and no new reading can be taken right now."
            )
        arm_device_for_user(user["id"])
        return "Device armed for this patient — their next capture on the shared sensor will be linked to their account."

    if has_phone:
        tools += [send_appointment_offer, send_post_appointment_followup, send_meal_checkin, send_wellness_checkin]
    tools += [update_patient_context, request_sensor_reading]

    # ---------------------------------------------------------------------
    # Screening tools — ported from guidance_agent.py (2026-08-20
    # orchestrator merge; that module is deleted). Async -> sync: guidance_
    # agent.run() executed on FastAPI's main event loop and needed
    # asyncio.to_thread()/await ws.broadcast() everywhere to avoid blocking
    # it. WhatsApp Agent already runs inside asyncio.to_thread(handle_trigger,
    # ...) — it's off the main loop before any tool ever runs — so these call
    # scoring/screening_llm directly and broadcast via _wa_emit, same as
    # every other tool in this file. None of scoring.py's deterministic math
    # or screening_llm.decide()'s narrow, separately-audited decision loop
    # changed even slightly; only who calls them did.
    # ---------------------------------------------------------------------
    @tool
    def run_screening_pipeline() -> str:
        """Claim the latest saliva reading into a new screening case and run
        the deterministic organ-screening pipeline (validate -> score
        KIDNEY/LIVER/ORAL -> single screening decision call). Call this
        first when triggered by a new sensor reading (sensor.reading_received)
        — it's the only source of the organ prediction, confidence, and flag.
        Don't call it for any other trigger, and don't call it twice in one run."""
        if not user:
            return "No account is linked to this phone number, so there's no reading to screen."
        if screening_state.get("screening_done"):
            return "The screening pipeline has already run this session; do not call it again."

        try:
            case_row = scoring.claim_new_case_from_latest_reading(user["id"])
        except Exception as exc:
            logger.exception("whatsapp_agent run_screening_pipeline: claim failed")
            return f"Could not claim a new screening case: {exc}"
        if case_row is None:
            return "No reading is available to screen."
        screening_state["case_row"] = case_row

        _wa_emit("validate", "start", "Validating reading")
        try:
            errors = scoring.validate_reading(case_row)
        except Exception as exc:
            _wa_emit("validate", "error", "Validation failed")
            logger.exception("whatsapp_agent run_screening_pipeline: validate failed")
            return f"Validation step raised an error: {exc}"

        if errors:
            reason = "; ".join(errors)
            _wa_emit("validate", "error", "Validation failed")
            scoring.mark_retest_required(case_row["id"], reason)
            screening_state["screening_done"] = True
            return (
                f"Validation failed ({reason}). The case has been marked RETEST_REQUIRED "
                "already — do not call request_retest for this."
            )
        _wa_emit("validate", "success", "Reading validated")

        values = {b: float(case_row[b]) for b in scoring.BIOMARKERS}
        engine = scoring.get_engine()
        node_map = {"KIDNEY": "score_kidney", "LIVER": "score_liver", "ORAL": "score_oral"}
        specialist_results = []
        for organ in scoring.ORGANS:
            node = node_map[organ]
            _wa_emit(node, "start", f"Scoring {organ.title()}")
            result = engine.evaluate(organ, values)
            specialist_results.append(result)
            _wa_emit(node, "success", f"{organ.title()} fit: {result['flag']}")

        try:
            decision, model, raw_result = screening_llm.decide(case_row, specialist_results)
        except screening_llm.HumanReviewRequested as exc:
            try:
                scoring.mark_retest_required(case_row["id"], exc.reason)
            except Exception as mark_exc:
                logger.exception(
                    "whatsapp_agent run_screening_pipeline: mark_retest_required failed after HumanReviewRequested"
                )
                screening_state["screening_done"] = True
                return f"The screening decision was flagged for human review, but saving that status failed: {mark_exc}"
            screening_state["screening_done"] = True
            screening_state["retest_requested"] = True
            return (
                f"The screening decision component flagged this case for human review "
                f"(reason: {exc.reason}). The case has already been marked RETEST_REQUIRED — "
                "do not call request_retest for this case."
            )
        except screening_llm.OpenRouterDecisionError:
            scoring.release_reading(case_row["id"])
            screening_state["screening_done"] = True
            return (
                "The screening decision call failed; the case was released back to NEW "
                "(no prediction saved). Consider calling request_retest."
            )

        scoring.persist_decision(case_row, decision, specialist_results, model, raw_result)
        flag = next((r["flag"] for r in specialist_results if r["organ"] == decision["prediction"]), "medium")
        matched_cases = next(
            (r["matched_cases"] for r in specialist_results if r["organ"] == decision["prediction"]), None
        )

        screening_state["screening_done"] = True
        screening_state["organ"] = decision["prediction"]
        screening_state["confidence"] = decision["confidence"]
        screening_state["flag"] = flag
        screening_state["reason"] = decision.get("reason")
        screening_state["matched_cases"] = matched_cases
        return (
            f"Screening complete. Predicted organ: {decision['prediction']}, "
            f"confidence: {decision['confidence']:.2f}, flag: {flag}. Use this to decide "
            "whether to generate a report, offer a clinic appointment, or (only if this "
            "had failed) request a retest."
        )

    @tool
    def generate_report() -> str:
        """Generate the plain-language screening report (per-area notes +
        recommendation) for this patient's latest reading, taking any
        doctor-provided context into account. Worth calling for medium/high
        flags, and often for low flags too."""
        if not user:
            return "No account is linked to this phone number, so there's no report to generate."
        row = reference_data.get_latest_row(user["id"])
        if not row:
            return "No reading available to generate a report from."
        reading = reference_data.row_to_reading(row)
        ctx = reference_data.get_context(user["id"])
        content_llm.report_agent(reading, ctx, user["id"], "en")
        screening_state.setdefault("action_tokens", []).append("report")
        return "Report generated and saved successfully — use send_report_pdf if the patient wants it sent as a document."

    @tool
    def request_retest(reason: str) -> str:
        """Flag the current case as needing a retest instead of guessing —
        use this only when run_screening_pipeline's validation failed or it
        could not produce a confident result. `reason` is a short explanation."""
        case_row = screening_state.get("case_row")
        if case_row:
            scoring.mark_retest_required(case_row["id"], reason)
        screening_state["retest_requested"] = True
        screening_state.setdefault("action_tokens", []).append("request_retest")
        return "Retest requested successfully."

    # Hard-gated, not just prompt-guided (2026-08-22): claim_new_case_from_
    # latest_reading has no dedup — a second call creates a genuinely new
    # screening_cases row and can send a second appointment offer. reading.
    # followup's own run always happens after sensor.reading_received's
    # already screened this same reading, so these tools are excluded
    # entirely there rather than trusted to the model's judgment.
    if allow_screening:
        tools += [run_screening_pipeline, generate_report, request_retest]
    return tools


_TRIGGER_DESCRIPTION = {
    "sensor.reading_received": (
        "A new saliva reading just arrived from the sensor. Call run_screening_pipeline first — "
        "never guess an organ or a flag yourself, and never skip straight to messaging the patient "
        "before you have a real result. Based on what it returns: generate_report is worth calling "
        "for medium/high flags, and often for low flags too. If a medium/high flag comes back, you "
        "should very likely also call send_appointment_offer if this patient has a phone on file "
        "(the code forces one anyway if you don't, per the safety guarantee — but use your own "
        "judgment on tone and whether to add anything else, like a written spoken-style summary). "
        "If the flag is low, a brief reassuring note is optional, not required — restraint is fine. "
        "If validation failed or the pipeline couldn't produce a confident result, call "
        "request_retest instead of guessing — never call it after a successful, confident screening. "
        "If this patient has no phone on file, none of the send/booking tools are available to you "
        "this run — screen, report, and remember what happened via update_patient_context; there's "
        "nowhere to message them, which is expected, not an error."
    ),
    "reading.followup": (
        f"This patient took a saliva reading about {config.READING_FOLLOWUP_DELAY_SECONDS // 60} minutes ago. "
        "A separate run already handled screening/report/appointment-offer for that reading immediately when "
        "it came in — do NOT call run_screening_pipeline here, this is not a second screening pass. This is "
        "purely a warm, personal wellness check-in: greet the patient by name, ask how they're feeling / how "
        "they're doing right now, and mention this is a quick follow-up from NOVERA's AI after their recent "
        "reading. Keep it light and caring, not clinical — you can glance at get_patient_facts for context if "
        "useful, but don't recite biomarker values or screening results here (that already happened "
        "separately); this message is about the person, not the numbers."
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
        (
            f"This phone number is linked to a registered patient account. Their name on file is "
            f"{user.get('name')!r} — use it sometimes to address them directly (e.g. an opening "
            "greeting), not in every single message, so it reads as natural rather than robotic."
            if user.get("name") else
            "This phone number is linked to a registered patient account, but no name is on file "
            "for them — just address them generically."
        )
        if user else
        "This phone number is NOT linked to any registered patient account, so there are no "
        "personal facts to retrieve for it — get_patient_facts will say so if called. Your reply "
        f"MUST include this exact signup link so they can register with this same phone number: "
        f"{config.SIGNUP_URL} — send it as plain text, never wrapped in markdown bold/italic "
        "(e.g. **like this** or _like this_), since that breaks WhatsApp's link auto-detection "
        "and the patient won't be able to tap it."
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
        "You have tools to look up this patient's real facts, run the deterministic organ-screening "
        "pipeline on their latest reading and generate their report, book/cancel/reschedule a REAL "
        "clinic appointment, send their report/a spoken-style summary/their natural-recovery self-care "
        "plan (what to eat and do to recover naturally), send proactive outreach messages (appointment "
        "offers, follow-ups, meal/wellness check-ins), arm the shared sensor device for their next "
        "reading, and write back what you learn into their persistent memory via update_patient_context. "
        "Every send/booking/device/screening tool has an immediate "
        "real-world effect — only call one when it's actually warranted, not reflexively.\n\n"
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
        "IMPORTANT: send_report_pdf, send_voice_note, send_self_care_plan, send_appointment_offer, "
        "send_post_appointment_followup, send_meal_checkin, and send_wellness_checkin already send a "
        "REAL WhatsApp message to the patient directly the moment you call them — their tool result is "
        "just a status confirmation for you, not something to relay. After calling one of these, do NOT "
        "write a patient-facing restatement of what you just sent; if there's nothing else left to do, "
        "stop immediately with a short internal note (e.g. 'sent the PDF report').\n\n"
        f"Keep any message warm and concise (2-5 sentences unless relaying a booking's full details), "
        f"entirely in {lang_name}. This is screening support, not medical advice. Meta's WhatsApp API "
        "only allows free-form replies within 24 hours of the patient's last message — that window is "
        "enforced in code (proactive send tools automatically fall back to an approved template outside "
        "it), not by you, but don't tell the patient you can message them again anytime unprompted. "
        "Any link or URL in your reply (signup link, map link, or otherwise) must be sent as plain "
        "text, never wrapped in markdown bold/italic (**like this** or _like this_) — that breaks "
        "WhatsApp's tap-to-open link detection."
    )


def _run_agent_loop(messages: list, tools: list) -> tuple[Optional[str], bool, bool]:
    """Shared loop for both entry points. Returns (final_text_or_None,
    hit_iteration_cap, self_send_fired) — self_send_fired is True if any
    _SELF_SENDING_TOOL_NAMES tool was called this run (see that constant's
    own comment for why the caller needs this to avoid a duplicate send)."""
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

    self_send_fired = False
    for _ in range(MAX_ITERATIONS):
        response = llm.invoke(messages)
        messages.append(response)
        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            if isinstance(response.content, str) and response.content.strip():
                return response.content.strip(), False, self_send_fired
            return None, False, self_send_fired
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
                    if name in _SELF_SENDING_TOOL_NAMES:
                        self_send_fired = True
                except Exception as exc:
                    logger.exception("whatsapp_agent tool %r raised", name)
                    result_text = f"Tool {name} raised an unexpected error: {exc}"
                    if wa_node:
                        _wa_emit(wa_node, "error", f"{name} failed")
            messages.append(ToolMessage(content=str(result_text), tool_call_id=call_id))
    return None, True, self_send_fired


def handle_inbound(from_number: str, text: str, lang: str = "en") -> str:
    """Reactive entry point: a patient sent a WhatsApp message. Almost always
    returns a non-empty reply string for the caller (routers/whatsapp.py's
    _process_and_reply) to send — never leaves the patient unanswered, even
    on total failure (degrades to _fallback_answer()).

    Bug fix (2026-08-23): the ONE exception is an empty string "" — returned
    specifically when a _SELF_SENDING_TOOL_NAMES tool already sent a real
    message directly this run, meaning the model's own trailing text would
    be a second, redundant send. Callers MUST check truthiness before
    sending, not send unconditionally.

    Admin/demo mode (2026-08-23): see _try_admin_trigger/_admin_session_
    active. `phone` always stays the real sending device's number (Meta
    replies must go there regardless of which account `user` resolves to)
    — only `user` ever changes to the admin account."""
    phone = normalize_phone(from_number)

    # Checked first, ahead of even the admin trigger — a real emergency takes
    # priority over every other path in this function, including whichever
    # account this number resolves to.
    if _is_emergency_message(text):
        logger.info("whatsapp_agent: emergency keyword match, phone=%s — hardcoded reply, no agent loop", phone)
        whatsapp_client.send_message(_emergency_reply(lang), to=from_number)
        return ""

    admin_row = _try_admin_trigger(from_number, text)
    if admin_row:
        whatsapp_context.mark_inbound(admin_row["id"])
        reply = _admin_intro_message(lang)
        result = whatsapp_client.send_message(reply, to=from_number)
        if result.get("delivered"):
            whatsapp_context.mark_outbound(admin_row["id"])
        # Bug fix (2026-08-23): this branch already sent `reply` directly above
        # — same self-send pattern as _SELF_SENDING_TOOL_NAMES, but this path
        # never goes through _run_agent_loop, so that fix didn't cover it.
        # Returning `reply` here made the caller (routers/whatsapp.py's
        # _process_and_reply) send it again, producing the reported duplicate.
        return ""

    user = _admin_session_user() if _admin_session_active(phone) else _find_user_by_phone(from_number)

    if user:
        whatsapp_context.mark_inbound(user["id"])

    if _is_plain_greeting(text):
        # Bug fix (2026-08-23, Hassan's call): a bare "hi"/"hey"/"hello
        # Novera" used to go through the full LLM agent loop for a message
        # with nothing to actually decide — answered here directly instead,
        # both for the instant feature-list menu and to save a full LLM
        # round-trip (same latency motivation as _SELF_SENDING_TOOL_NAMES).
        reply = _greeting_reply(user, lang)
        result = whatsapp_client.send_message(reply, to=from_number)
        if result.get("delivered") and user:
            whatsapp_context.mark_outbound(user["id"])
        return ""

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
    self_send_fired = False
    try:
        reply, hit_cap, self_send_fired = _run_agent_loop(messages, tools)
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
        if self_send_fired:
            # Bug fix (2026-08-23): a send_report_pdf/send_voice_note/
            # send_self_care_plan/send_appointment_offer/send_post_appointment_
            # followup/send_meal_checkin/send_wellness_checkin tool already sent
            # a real message directly this run — this `reply` is the model's own
            # trailing restatement of that, which the caller (routers/whatsapp.py's
            # _process_and_reply) would otherwise send AGAIN as a second, redundant
            # message. Empty string, not `reply` — the caller checks truthiness
            # before sending (see its own updated comment).
            logger.info(
                "whatsapp_agent: suppressing duplicate trailing reply after a self-sending tool, phone=%s: %r",
                phone, reply,
            )
            return ""
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


def _narrate_screening(screening_state: dict[str, Any]) -> None:
    """Ported from guidance_agent.run() (2026-08-20 orchestrator merge) —
    decorative reasoning-stream ticker lines for the homepage diagram, fired
    once run_screening_pipeline actually produced a result this run. Fully
    best-effort: reasoning_stream.generate_reasoning_stream() already returns
    None on any failure (see its own docstring), and this whole function is
    called from inside handle_trigger's try/except, so a failure here can
    never break the actual screening/messaging work that already happened."""
    narration_lines = reasoning_stream.generate_reasoning_stream(
        screening_state.get("organ"),
        screening_state.get("confidence"),
        screening_state.get("reason") or "",
        screening_state.get("flag"),
        screening_state.get("matched_cases"),
        screening_state.get("action_tokens", []),
    )
    if not narration_lines:
        return
    for line in narration_lines:
        clean_line = line[2:] if line.startswith("> ") else line
        ws.broadcast_from_thread({"type": "narration", "source": "whatsapp", "label": clean_line})


def handle_trigger(trigger: str, user: dict[str, Any], payload: Optional[dict[str, Any]] = None, lang: str = "en") -> None:
    """Proactive entry point: woken by something other than a patient message
    (see PROACTIVE_TRIGGERS). Requires an already-resolved, registered `user`.
    Fires and forgets: no reply is returned to a caller, since there's no
    inbound request to reply to. The model may legitimately decide to send
    nothing — that's success, not failure, logged as such.

    sensor.reading_received is the one trigger that runs without a phone on
    file (2026-08-20 orchestrator merge) — screening must still happen for
    every account, phone or not; see _build_tools' has_phone gating for what
    that does and doesn't make available. Every other trigger still requires
    a phone, since proactive WhatsApp outreach has nowhere to go without one."""
    if trigger not in PROACTIVE_TRIGGERS:
        logger.error("whatsapp_agent.handle_trigger: unknown trigger %r", trigger)
        return
    phone = normalize_phone(user.get("phone") or "")
    if not phone and trigger != "sensor.reading_received":
        logger.info("whatsapp_agent.handle_trigger: user_id=%s has no phone on file, skipping trigger=%s",
                    user.get("id"), trigger)
        return

    is_reading_trigger = trigger == "sensor.reading_received"
    if is_reading_trigger and not _try_acquire_reading_run():
        # Throttled — emits nothing and fails silently, same behavior
        # guidance_agent.py's throttle always had.
        return

    try:
        # Safety floor (spec §6): forced, not suggested. For every trigger
        # except sensor.reading_received, the latest completed screening is
        # already settled by the time the trigger fires, so checking it
        # before the model gets a turn is correct — a general net in case a
        # medium/high flag somehow wasn't already handled by its own
        # trigger. For sensor.reading_received specifically, THIS run's
        # screening hasn't happened yet at this point — checking now would
        # only ever see the *previous* completed case's flag. That check
        # moves to after the loop below, once run_screening_pipeline has
        # actually persisted a decision.
        if not is_reading_trigger:
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
        screening_state: dict[str, Any] = {}
        tools = _build_tools(
            user, phone, lang, within_window=within_window, screening_state=screening_state,
            allow_screening=(trigger != "reading.followup"),
            # handle_trigger is exclusively the proactive/autonomous path (see
            # this function's own docstring) — never let an autonomous run
            # commit a real booking/cancellation on its own judgment. If the
            # patient replies to an offer, that reply comes in through
            # handle_inbound instead, where booking tools are available again.
            allow_booking=False,
        )

        payload_line = f"\n\nTrigger payload: {payload}" if payload else ""
        messages: list = [
            SystemMessage(content=_system_prompt(user, lang, trigger=trigger)),
            HumanMessage(content=f"Trigger fired: {trigger}{payload_line}"),
        ]
        wa_trigger_node = _TRIGGER_TO_NODE[trigger]
        _wa_emit(wa_trigger_node, "start", f"{trigger} fired")
        _wa_emit("wa_agent", "start", "WhatsApp Agent deciding")
        try:
            # self_send_fired unused here — handle_trigger never re-sends
            # `reply` as a message itself (only logs it as a note below); the
            # duplicate-send risk _run_agent_loop's 3rd return value guards
            # against is specific to handle_inbound's caller, which does.
            reply, hit_cap, _self_send_fired = _run_agent_loop(messages, tools)
            if hit_cap:
                logger.info("whatsapp_agent.handle_trigger: hit iteration cap for trigger=%s user_id=%s",
                            trigger, user["id"])
            logger.info("whatsapp_agent.handle_trigger: trigger=%s user_id=%s completed, model note=%r",
                        trigger, user["id"], reply)

            if is_reading_trigger and screening_state.get("organ"):
                try:
                    _narrate_screening(screening_state)
                except Exception:
                    logger.exception("whatsapp_agent.handle_trigger: reasoning-stream narration failed for user_id=%s", user["id"])
                # Post-screening safety floor (see the comment above where the
                # pre-loop check is skipped for this trigger) — runs now that
                # this run's own decision is actually persisted. If the agent's
                # own loop already sent an offer this run, mark_outbound already
                # moved last_outbound_at to "now", so enforce_outreach_guarantee's
                # own cooldown check naturally no-ops here instead of double-sending.
                try:
                    forced = whatsapp_gating.enforce_outreach_guarantee(user)
                    if forced:
                        logger.info(
                            "whatsapp_agent.handle_trigger: post-screening safety-floor outreach forced for user_id=%s",
                            user["id"],
                        )
                except Exception:
                    logger.exception(
                        "whatsapp_agent.handle_trigger: post-screening enforce_outreach_guarantee failed for user_id=%s",
                        user["id"],
                    )

            _wa_emit(wa_trigger_node, "success", f"{trigger} handled")
            # Coarse, non-identifying label only — `reply` is the model's own
            # free-form note and may reference patient-specific details (already
            # logged server-side only, above); never put it on the public socket,
            # same discipline guidance_agent.py's _summarize() docstring explained.
            _wa_emit("wa_agent", "success", "Decided to act" if reply else "Stayed quiet — no message needed")
            _wa_run_end(f"WhatsApp Agent handled {trigger}")
        except Exception:
            logger.exception("whatsapp_agent.handle_trigger: agent loop failed for trigger=%s user_id=%s",
                              trigger, user["id"])
            _wa_emit(wa_trigger_node, "error", f"{trigger} failed")
            _wa_emit("wa_agent", "error", "Run failed")
            _wa_run_end(f"WhatsApp Agent run failed ({trigger})")
    finally:
        if is_reading_trigger:
            _release_reading_run()
