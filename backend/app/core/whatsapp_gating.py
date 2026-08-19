"""The forced, non-model-discretionary safety floor (spec §6): a medium/high
screening flag guarantees the patient gets contacted, no exceptions — this
moved here from Guidance Agent's old hardcoded `offer_clinic_appointment`
(which only ever simulated), now a real deterministic wrapper the model
cannot skip. Runs BEFORE the WhatsApp Agent's model gets a turn, same as the
spec's own framing: "Forced, not suggested."
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from . import scoring, whatsapp_context, whatsapp_templates
from ..security import normalize_phone

logger = logging.getLogger(__name__)

OUTREACH_COOLDOWN_HOURS = 24


def _hours_since(ts: Optional[datetime]) -> Optional[float]:
    if ts is None:
        return None
    return (datetime.now(timezone.utc) - ts).total_seconds() / 3600


def enforce_outreach_guarantee(user: dict[str, Any]) -> bool:
    """Called for a specific registered user (one per phone number texting
    the bot — see novera-project memory on the single-patient/multi-account
    scope decision). Returns True if a forced appointment offer was sent."""
    latest = scoring.get_latest_screening_flag()
    if not latest or latest["flag"] not in ("medium", "high"):
        return False

    phone = normalize_phone(user.get("phone") or "")
    if not phone:
        return False

    context = whatsapp_context.get_or_create(user["id"])
    hours_since_contact = _hours_since(context.get("last_outbound_at"))
    if hours_since_contact is not None and hours_since_contact <= OUTREACH_COOLDOWN_HOURS:
        return False

    patient_name = user.get("name") or "there"
    result = whatsapp_templates.send_appointment_offer(
        context=context,
        to=phone,
        patient_name=patient_name,
        organ=latest["organ"],
        case_id=latest["case_id"],
    )
    whatsapp_context.mark_outbound(user["id"])
    whatsapp_context.append_conversation_note(
        user["id"],
        f"[forced outreach] {latest['flag']} flag on {latest['organ']} — appointment offer sent "
        f"(delivered={result.get('delivered')})",
    )
    logger.info(
        "whatsapp_gating enforce_outreach_guarantee: user_id=%s organ=%s flag=%s delivered=%s",
        user["id"], latest["organ"], latest["flag"], result.get("delivered"),
    )
    return True
