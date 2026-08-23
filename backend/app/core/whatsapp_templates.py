"""The 5-template library the autonomous WhatsApp Agent needs (spec §5), plus
the shared 24h-window-gated send helper every proactive tool uses.

IMPORTANT — external dependency, not yet satisfied: `TEMPLATE_NAME` below
must be created and APPROVED in Meta Business Manager (WhatsApp Manager ->
Message Templates) before any of this can actually send outside the 24h
window. That's a manual step outside this codebase with real approval lead
time (Meta review, not instant) — this file has the body text and variable
count each template needs, ready to paste into that submission, but nothing
here can complete the approval itself. Until approved, calls to
whatsapp_client.send_template_message() will fail gracefully (logged,
`delivered: False`) exactly like any other misconfigured send in this
codebase — proactive outreach simply won't reach the patient outside the
window until this is done.

The `_freeform_*` functions are the within-24h-window alternative — real,
working today, no external dependency, used whenever the patient has
messaged in the last 24h so free-form text is actually allowed.
"""
from __future__ import annotations

from typing import Any, Optional

from .. import config
from . import clinic, whatsapp_client

# Meta template names — must match exactly what's submitted for approval.
TEMPLATE_NAME = {
    "appointment_offer": "novera_appointment_offer",
    "appointment_followup": "novera_appointment_followup",
    "meal_checkin": "novera_meal_checkin",
    "wellness_checkin": "novera_wellness_checkin",
    "retest_reminder": "novera_retest_reminder",
}

# Body text for each template, {N} placeholders shown for reference — submit
# these to Meta with {{1}}, {{2}}... in their body exactly in this order.
TEMPLATE_BODY_FOR_APPROVAL = {
    "appointment_offer": (
        "Hi {1}, your latest NOVERA screening flagged your {2} health as worth a follow-up. "
        "Would you like us to book you an appointment at {3}, {4}? Reply YES to book or NO to skip."
    ),
    "appointment_followup": (
        "Hi {1}, how did your {2} appointment at {3} go? Let us know if you have any questions, "
        "or reply REPORT if you'd like your screening report resent."
    ),
    "meal_checkin": (
        "Hi {1}, quick check-in: did you manage to follow today's self-care food guidance? "
        "Reply YES, NO, or tell me what happened."
    ),
    "wellness_checkin": (
        "Hi {1}, checking in — how have you been feeling since your last NOVERA screening? "
        "Let us know if anything's changed."
    ),
    "retest_reminder": (
        "Hi {1}, your last NOVERA reading couldn't produce a confident result "
        "({2}). Whenever you're able, a fresh reading would help us follow up properly."
    ),
}


def _send_gated(
    *,
    context: dict[str, Any],
    to: str,
    freeform_text: str,
    template_key: str,
    template_vars: list[str],
    lang_code: str = "en",
) -> dict[str, Any]:
    """The one place the 24h-window decision actually gets made (spec §5 —
    "cannot be left to the model's judgment"). Every proactive-send tool in
    whatsapp_agent.py routes through this instead of picking freeform vs.
    template itself."""
    from . import whatsapp_context  # local import: avoids a context<->templates cycle

    if whatsapp_context.within_24h_window(context):
        result = whatsapp_client.send_message(freeform_text, to=to)
    else:
        result = whatsapp_client.send_template_message(
            TEMPLATE_NAME[template_key], template_vars, to=to, lang_code=lang_code
        )
    return result


def send_appointment_offer(context: dict[str, Any], to: str, patient_name: str, organ: str, case_id: Optional[str]) -> dict[str, Any]:
    """Doctor naming (2026-08-23, Hassan's call): when clinic.doctor_for_organ
    has a real doctor on file for this organ, the freeform offer names them
    and gives one condensed line on their background instead of a generic
    "book a follow-up" — see clinic.DOCTORS for why it's deliberately terse
    (one line, not the doctor's full bio) and organ-scoped (never claims a
    doctor for an organ they weren't actually assigned to).

    Freeform-only for now: the pre-approved Meta template (used outside the
    24h window) still has its original 4 variables — adding a 5th (doctor
    name) means resubmitting that template body to Meta for re-approval,
    a manual step outside this codebase (see this module's own docstring).
    Until that happens, a patient outside the window gets the organ-only
    template text, no doctor name — a real, temporary asymmetry with the
    freeform path, not a bug."""
    ref = f" (ref {case_id})" if case_id else ""
    doctor = clinic.doctor_for_organ(organ)
    if doctor:
        freeform = (
            f"Hi {patient_name}, your latest NOVERA screening flagged your {organ.lower()} health as worth "
            f"a follow-up{ref}. We'd suggest {doctor['name']}, {doctor['blurb']}. Would you like me to book "
            f"an appointment with {doctor['name']} at {config.CLINIC_NAME}, {config.CLINIC_BRANCH}? "
            "Reply YES to book or NO to skip."
        )
    else:
        freeform = (
            f"Hi {patient_name}, your latest NOVERA screening flagged your {organ.lower()} health as worth "
            f"a follow-up{ref}. Would you like me to book an appointment at {config.CLINIC_NAME}, "
            f"{config.CLINIC_BRANCH}? Reply YES to book or NO to skip."
        )
    return _send_gated(
        context=context,
        to=to,
        freeform_text=freeform,
        template_key="appointment_offer",
        template_vars=[patient_name, organ.lower(), config.CLINIC_NAME, config.CLINIC_BRANCH],
    )


def send_appointment_followup(context: dict[str, Any], to: str, patient_name: str, organ: str) -> dict[str, Any]:
    freeform = (
        f"Hi {patient_name}, how did your {organ.lower()} appointment at {config.CLINIC_NAME} go? "
        "Let me know if you have any questions, or ask any time for your screening report."
    )
    return _send_gated(
        context=context,
        to=to,
        freeform_text=freeform,
        template_key="appointment_followup",
        template_vars=[patient_name, organ.lower(), config.CLINIC_NAME],
    )


def send_meal_checkin(context: dict[str, Any], to: str, patient_name: str) -> dict[str, Any]:
    freeform = (
        f"Hi {patient_name}, quick check-in: did you manage to follow today's self-care food guidance? "
        "Reply with how it went — even a quick yes/no helps me track your plan."
    )
    return _send_gated(
        context=context,
        to=to,
        freeform_text=freeform,
        template_key="meal_checkin",
        template_vars=[patient_name],
    )


def send_wellness_checkin(context: dict[str, Any], to: str, patient_name: str) -> dict[str, Any]:
    freeform = (
        f"Hi {patient_name}, checking in — how have you been feeling since your last NOVERA screening? "
        "Let me know if anything's changed."
    )
    return _send_gated(
        context=context,
        to=to,
        freeform_text=freeform,
        template_key="wellness_checkin",
        template_vars=[patient_name],
    )


def send_retest_reminder(context: dict[str, Any], to: str, patient_name: str, reason: str) -> dict[str, Any]:
    freeform = (
        f"Hi {patient_name}, your last NOVERA reading couldn't produce a confident result ({reason}). "
        "Whenever you're able, a fresh reading would help us follow up properly."
    )
    return _send_gated(
        context=context,
        to=to,
        freeform_text=freeform,
        template_key="retest_reminder",
        template_vars=[patient_name, reason],
    )
