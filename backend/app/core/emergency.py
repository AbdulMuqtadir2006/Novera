"""Shared, deterministic emergency-message detection (2026-08-26) — used by
both the WhatsApp agent and the website self-care chat so a patient
describing a real medical emergency gets the same hardcoded redirect
regardless of which surface they're on, and so both stay in sync if the
phrase list ever changes. Deliberately NOT an LLM call: if something matters
this much, don't trust it to a model call that could fail, drift, or get
talked out of redirecting.
"""
from __future__ import annotations

import re

# Matches ANYWHERE in the message (not a whole-message match) since a real
# emergency is rarely phrased as a bare keyword. Kept to high-specificity
# phrases only (no bare "pain") so an ordinary question ("is mild stomach
# pain normal after eating?") never gets hijacked into this reply.
_EMERGENCY_RE = re.compile(
    r"(can'?t breathe|cannot breathe|chest pain|heart attack|having a stroke|"
    r"severe bleeding|bleeding heavily|suicidal|kill myself|want to die|"
    r"hurt myself|harm myself|end my life|overdose|need an ambulance|"
    r"لا أستطيع التنفس|ألم في الصدر|نوبة قلبية|سكتة دماغية|نزيف حاد|"
    r"أريد أن أموت|أفكر في الانتحار|أؤذي نفسي|أحتاج إسعاف)",
    re.IGNORECASE,
)


def is_emergency_message(text: str) -> bool:
    return bool(_EMERGENCY_RE.search((text or "").strip()))


def reply(lang: str) -> str:
    if lang == "ar":
        return (
            "🚨 نوفيرا أداة فحص أولي وليست خدمة طوارئ. إذا كانت هذه حالة طارئة حقيقية، يرجى "
            "الاتصال فورًا بالرقم 9999 (الطوارئ في عُمان) أو التوجه إلى أقرب قسم طوارئ الآن."
        )
    return (
        "🚨 NOVERA is a screening tool, not an emergency service. If this is a real medical "
        "emergency, please call 9999 (Oman's emergency number) or go to the nearest ER right now."
    )
