"""The 12 agent nodes + routing functions (brief §6, §8).

LLM steps reuse the shared OpenRouter layer with deterministic fallbacks, so the
whole pipeline runs today; the API-key swap (Claude/WhatsApp/TTS) is the final
step. The one non-negotiable rule: `threshold_crossed` is set ONLY by the Python
`check_threshold()` gate — never by an LLM.
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from .. import clinic, config, whatsapp
from ..llm import LLMError, structured_json_call, text_call
from . import db
from .report import build_report_pdf
from .state import (
    AREA_MARKERS,
    DISCLAIMER,
    HEALTH_AREAS,
    NoveraState,
    REFERENCE,
    check_threshold,
)


def _lang(state: NoveraState) -> str:
    return (state.get("user_context", {}) or {}).get("language", "en") or "en"


def _lang_name(lang: str) -> str:
    return "Arabic" if lang == "ar" else "English"


def _status_for(value: float, rng: list[float], pad: float = 0.12) -> str:
    low, high = rng
    span = high - low
    p = span * pad
    if value < low - p or value > high + p:
        return "concern"
    if value < low or value > high:
        return "watch"
    return "normal"


# ---------------------------------------------------------------- Agent 2: Capture
def capture_agent(state: NoveraState) -> dict[str, Any]:
    user = db.get_user(state["user_id"]) or {}
    ctx = state.get("user_context") or {
        "name": user.get("name", "there"),
        "phone": user.get("phone", ""),
        "language": user.get("language", "en"),
        "diet": user.get("diet", ""),
        "exercise": user.get("exercise", ""),
        "age": user.get("age"),
    }
    reading = state.get("raw_reading", {}) or {}
    errors = []
    for f in ("ph", "creatinine", "urea", "temperature"):
        try:
            reading[f] = float(reading[f])
        except (KeyError, TypeError, ValueError):
            errors.append(f)
    out: dict[str, Any] = {
        "user_context": ctx,
        "raw_reading": reading,
        "trace": ["capture"],
    }
    if "qa_loop_count" not in state:
        out["qa_loop_count"] = 0
    if errors:
        out["error"] = f"Missing/invalid fields: {', '.join(errors)}"
    return out


# ---------------------------------------------------------------- Agent 3: Confidence/QA (deterministic)
def confidence_qa_agent(state: NoveraState) -> dict[str, Any]:
    r = state.get("raw_reading", {})
    score = 1.0
    reasons = []
    ph = float(r.get("ph", 7))
    temp = float(r.get("temperature", 36.6))
    creat = float(r.get("creatinine", 1))
    urea = float(r.get("urea", 15))
    if not (5.0 <= ph <= 8.5):
        score -= 0.45; reasons.append(f"pH {ph} outside plausible sensor range")
    elif not (6.0 <= ph <= 8.0):
        score -= 0.12; reasons.append(f"pH {ph} borderline")
    if not (34.0 <= temp <= 39.0):
        score -= 0.4; reasons.append(f"temperature {temp}°C likely environment contamination")
    if not (0.1 <= creat <= 5.0):
        score -= 0.3; reasons.append(f"creatinine {creat} outside plausible saliva range")
    if not (1.0 <= urea <= 60.0):
        score -= 0.3; reasons.append(f"urea {urea} outside plausible saliva range")
    if state.get("error"):
        score -= 0.5; reasons.append(state["error"])
    score = max(0.0, min(1.0, round(score, 2)))
    return {
        "confidence_score": score,
        "confidence_reason": "; ".join(reasons) or "All biomarkers physiologically plausible.",
        "qa_passed": score >= 0.7,
        "trace": ["qa"],
    }


# ---------------------------------------------------------------- Agent 1: Orchestrator (Boss) — decision #1
def orchestrator_node(state: NoveraState) -> dict[str, Any]:
    loop = int(state.get("qa_loop_count", 0))
    conf = float(state.get("confidence_score", 0))
    decision = "analysis"
    if loop >= 2:
        decision = "analysis"  # never loop forever
    else:
        # Agentic decision — Boss LLM call (falls back to the documented rule).
        try:
            word = text_call(
                system="You are the Orchestrator for Novera, a health screening AI. Answer with exactly one word.",
                user=(
                    f"Confidence score: {conf}\nReason: {state.get('confidence_reason','')}\n"
                    f"Loop count: {loop}\n\nRules: if confidence >= 0.7 -> analysis; "
                    f"if < 0.7 and loop < 2 -> capture; else analysis.\n"
                    f'Respond with exactly one word: "analysis" or "capture".'
                ),
                max_tokens=6,
                temperature=0,
            ).strip().lower()
            decision = "capture" if "capture" in word else "analysis"
        except LLMError:
            decision = "analysis" if conf >= 0.7 else "capture"
    out: dict[str, Any] = {"_route_after_qa": decision, "trace": [f"orchestrator→{decision}"]}
    if decision == "capture":
        out["qa_loop_count"] = loop + 1
    return out


def orchestrator_route_after_qa(state: NoveraState) -> str:
    return state.get("_route_after_qa", "analysis")


# ---------------------------------------------------------------- Agent 4: Analysis (LLM) + hardcoded gate
class _Area(BaseModel):
    area: str
    status: str = Field(pattern="^(normal|watch|concern)$")
    severity: int = Field(ge=0, le=10)
    key_finding: str


class _AnalysisOut(BaseModel):
    areas: list[_Area]
    flagged_domains: list[str]


def _deterministic_analysis(reading: dict, lang: str) -> tuple[dict, list]:
    results = {}
    flagged = []
    worst_rank = {"normal": 0, "watch": 1, "concern": 2}
    for area in HEALTH_AREAS:
        statuses = []
        for m in AREA_MARKERS[area]:
            statuses.append(_status_for(float(reading.get(m, REFERENCE[m]["range"][0])), REFERENCE[m]["range"]))
        status = max(statuses, key=lambda s: worst_rank[s])
        severity = {"normal": 1, "watch": 5, "concern": 8}[status]
        finding = {
            "en": {"normal": f"{area} markers are within range.",
                   "watch": f"{area} markers are drifting from the normal range.",
                   "concern": f"{area} markers are outside the reference range."},
            "ar": {"normal": f"مؤشرات {area} ضمن المعدل.",
                   "watch": f"مؤشرات {area} تبتعد عن المعدل الطبيعي.",
                   "concern": f"مؤشرات {area} خارج المعدل المرجعي."},
        }[lang if lang in ("en", "ar") else "en"][status]
        results[area] = {"status": status, "severity": severity, "key_finding": finding}
        if status in ("watch", "concern"):
            flagged.append(area)
    return results, flagged


def analysis_agent(state: NoveraState) -> dict[str, Any]:
    reading = state["raw_reading"]
    lang = _lang(state)
    ranges = {k: REFERENCE[k]["range"] for k in REFERENCE}
    try:
        out = structured_json_call(
            system=(
                "You are the Analysis Agent for Novera, a saliva-based screening system. Analyse each biomarker "
                "against its reference range and, for each of the four health areas (Kidney Health, Hydration, Oral "
                "Health, Digestive Health), give status (normal|watch|concern), severity (0-10), and a one-sentence "
                f"key_finding written in {_lang_name(lang)}. flagged_domains lists areas with status watch or concern."
            ),
            user=json.dumps({"reading": reading, "reference_ranges": ranges,
                             "user_context": state.get("user_context", {})}, ensure_ascii=False),
            model_cls=_AnalysisOut,
            max_tokens=900,
            temperature=0.2,
        )
        results = {a.area: {"status": a.status, "severity": a.severity, "key_finding": a.key_finding} for a in out.areas}
        flagged = out.flagged_domains
        # ensure all 4 areas present
        if set(results) != set(HEALTH_AREAS):
            raise LLMError("incomplete areas")
    except LLMError as exc:
        print(f"[analysis] fallback: {exc}")
        results, flagged = _deterministic_analysis(reading, lang)

    # HARDCODED SAFETY GATE — Python only.
    crossed, details = check_threshold(reading)

    reading_id = db.save_reading(state["user_id"], reading, float(state.get("confidence_score", 0)), bool(state.get("qa_passed")))
    db.save_analysis(reading_id, state["user_id"], results, flagged, crossed, details)

    return {
        "analysis_results": results,
        "flagged_domains": flagged,
        "threshold_crossed": crossed,
        "threshold_details": details,
        "reading_id": reading_id,
        "trace": ["analysis"],
    }


def threshold_gate(state: NoveraState) -> str:
    """Hardcoded safety gate (brief §8). Deterministic — never an LLM call."""
    return "escalate" if state.get("threshold_crossed", False) else "proceed"


# ---------------------------------------------------------------- Agent 5: Insight
def insight_agent(state: NoveraState) -> dict[str, Any]:
    lang = _lang(state)
    name = state.get("user_context", {}).get("name", "")
    try:
        text = text_call(
            system=(
                f"You are the Insight Agent for Novera. Explain screening results in clear, warm, plain "
                f"{_lang_name(lang)} — no clinical jargon (say 'your kidneys', not 'renal function'). Positive but "
                f"brief for normal findings; matter-of-fact (not alarming) for watch findings. Do NOT say 'see a "
                f"doctor'. Connect related findings. Max ~180 words, flowing paragraphs."
            ),
            user=json.dumps({"name": name, "analysis_results": state.get("analysis_results", {}),
                             "flagged_domains": state.get("flagged_domains", [])}, ensure_ascii=False),
            max_tokens=500,
        )
    except LLMError:
        flagged = state.get("flagged_domains", [])
        if lang == "ar":
            text = (f"مرحباً {name}. " + ("جميع مجالاتك الصحية تبدو ضمن المعدل الطبيعي." if not flagged
                    else f"معظم مؤشراتك جيدة، لكن يستحق المتابعة: {'، '.join(flagged)}.") + f" {DISCLAIMER}")
        else:
            text = (f"Hi {name}. " + ("All of your health areas look within a normal range." if not flagged
                    else f"Most of your markers look good; worth keeping an eye on: {', '.join(flagged)}.") + f" {DISCLAIMER}")
    return {"insight_text": text, "trace": ["insight"]}


# ---------------------------------------------------------------- Agent 6: Guidance
def guidance_agent(state: NoveraState) -> dict[str, Any]:
    lang = _lang(state)
    ctx = state.get("user_context", {})
    try:
        text = text_call(
            system=(
                f"You are the Guidance Agent for Novera. Create a personalised self-care plan in {_lang_name(lang)} "
                f"specific to the user's stated habits (diet/exercise). Structure it as Today (1-2 actions), This Week "
                f"(2-3 habits), and Retest (when to take the next reading). If nothing is flagged give maintenance "
                f"guidance. Never recommend medication or procedures. Max ~220 words."
            ),
            user=json.dumps({"analysis_results": state.get("analysis_results", {}),
                             "flagged_domains": state.get("flagged_domains", []), "user_context": ctx}, ensure_ascii=False),
            max_tokens=650,
        )
    except LLMError:
        if lang == "ar":
            text = ("اليوم: اشرب كوب ماء الآن وقلّل الملح في وجبتك القادمة.\n"
                    "هذا الأسبوع: وزّع شرب الماء على مدار اليوم، وأضف ٥٠٠ مل ماء قبل تمارينك.\n"
                    "إعادة الفحص: خذ قراءة جديدة بعد ٧ أيام.")
        else:
            text = ("Today: drink a glass of water now and go easy on salt in your next meal.\n"
                    "This week: spread your water intake across the day, and add 500 mL of water before your workout.\n"
                    "Retest: take a fresh reading in 7 days.")
    return {"guidance_plan": text, "trace": ["guidance"]}


# ---------------------------------------------------------------- Agent 7: Voice (script; TTS seam)
def voice_agent(state: NoveraState) -> dict[str, Any]:
    lang = _lang(state)
    insight = state.get("insight_text", "")
    try:
        script = text_call(
            system=(
                f"You are the Voice Agent for Novera. Rewrite the explanation for spoken narration in "
                f"{_lang_name(lang)}: short sentences, natural rhythm, no parenthetical clauses, no markdown. "
                f"Keep it under 8 sentences."
            ),
            user=insight,
            max_tokens=400,
        )
    except LLMError:
        script = insight
    # NOTE: TTS audio generation (Arabic + English) is wired at the API-key step.
    return {"voice_script": script, "trace": ["voice"]}


# ---------------------------------------------------------------- Agent 8: Report (PDF)
def report_agent(state: NoveraState) -> dict[str, Any]:
    path = build_report_pdf(dict(state))
    db.save_outputs(
        state.get("reading_id", ""), state["user_id"], state.get("insight_text", ""),
        state.get("guidance_plan", ""), state.get("voice_script", ""), "", path,
    )
    return {"report_path": path, "trace": ["report"]}


# ---------------------------------------------------------------- Agent 9: WhatsApp Notifier
def whatsapp_notifier_agent(state: NoveraState) -> dict[str, Any]:
    ctx = state.get("user_context", {})
    name = ctx.get("name", "")
    lang = _lang(state)
    if lang == "ar":
        body = (f"مرحباً {name}، كشف فحص نوفيرا الصحي عن شيء قد يحتاج إلى اهتمام الطبيب. هل تودّ:\n\n"
                "١. حجز موعد مع الطبيب\n٢. استلام تقرير صحتك الكامل\n\nأجب بـ ١ أو ٢، أو أخبرنا بما تريد.")
    else:
        body = (f"Hi {name}, your Novera health screening flagged something that may need a doctor's attention. "
                "Would you like to:\n\n1. Book a doctor's appointment\n2. Receive your full health report\n\n"
                "Reply 1 or 2, or just tell us what you'd like.")
    whatsapp.send_message(body, to=ctx.get("phone") or None, simulate=not config.WHATSAPP_ENABLED)
    return {"whatsapp_message_sent": True, "trace": ["whatsapp_notifier"]}


# ---------------------------------------------------------------- Agent 12: Multi-Language (lang + intent)
class _WhatsAppOut(BaseModel):
    detected_language: str
    intent: str = Field(pattern="^(book_appointment|send_report|explain_more|decline)$")


def _keyword_intent(msg: str) -> tuple[str, str]:
    t = msg.strip().lower()
    lang = "ar" if any("؀" <= ch <= "ۿ" for ch in msg) else "en"
    if "1" in t or "book" in t or "appointment" in t or "موعد" in t or "حجز" in t or "١" in msg:
        return lang, "book_appointment"
    if "2" in t or "report" in t or "تقرير" in t or "٢" in msg:
        return lang, "send_report"
    if "explain" in t or "why" in t or "اشرح" in t or "لماذا" in t:
        return lang, "explain_more"
    if "no" in t or "decline" in t or "لا" in t:
        return lang, "decline"
    return lang, "explain_more"


def multi_language_agent(state: NoveraState) -> dict[str, Any]:
    msg = state.get("whatsapp_reply", "")
    try:
        out = structured_json_call(
            system=("Analyse a patient's WhatsApp reply to a screening notification. Return the ISO 639-1 "
                    "detected_language and the intent (book_appointment | send_report | explain_more | decline)."),
            user=f"Message: {msg!r}",
            model_cls=_WhatsAppOut,
            max_tokens=120,
            temperature=0,
        )
        lang, intent = out.detected_language, out.intent
    except LLMError:
        lang, intent = _keyword_intent(msg)

    ctx = dict(state.get("user_context", {}))
    switched = ctx.get("language") != lang
    ctx["language"] = lang
    if state.get("user_id"):
        db.update_user_language(state["user_id"], lang)
    return {
        "detected_language": lang,
        "whatsapp_intent": intent,
        "language_switched": switched,
        "user_context": ctx,
        "trace": [f"multi_language→{intent}"],
    }


def route_whatsapp_intent(state: NoveraState) -> str:
    return state.get("whatsapp_intent", "decline")


# explain_more: regenerate the insight in the user's language and send it via WhatsApp
def explain_more_agent(state: NoveraState) -> dict[str, Any]:
    out = insight_agent(state)
    ctx = state.get("user_context", {})
    whatsapp.send_message(out["insight_text"], to=ctx.get("phone") or None, simulate=not config.WHATSAPP_ENABLED)
    return {"insight_text": out["insight_text"], "trace": ["explain_more"]}


# ---------------------------------------------------------------- Agent 10: Appointment Booking
def appointment_booking_agent(state: NoveraState) -> dict[str, Any]:
    ctx = state.get("user_context", {})
    lang = _lang(state)
    appt = db.book_nearest_slot(state["user_id"], state.get("reading_id"))
    if not appt:
        body = "Sorry, no appointment slots are available right now." if lang != "ar" else "عذراً، لا توجد مواعيد متاحة حالياً."
        whatsapp.send_message(body, to=ctx.get("phone") or None, simulate=not config.WHATSAPP_ENABLED)
        return {"appointment_booked": False, "trace": ["appointment_booking"]}

    loc = clinic.location()
    when = appt["slot_datetime"].replace("T", " ")
    if lang == "ar":
        body = (f"✅ تم حجز موعدك في {loc['name']}، {loc['branch']}.\n🗓 {when}\n👨‍⚕ {appt['doctor_name']}\n"
                f"رقم التأكيد: {appt['confirmation_number']}\n🗺 {loc['maps_url']}")
    else:
        body = (f"✅ Your appointment at {loc['name']}, {loc['branch']} is booked.\n🗓 {when}\n"
                f"👨‍⚕ {appt['doctor_name']}\nConfirmation: {appt['confirmation_number']}\n🗺 {loc['maps_url']}")
    whatsapp.send_message(body, to=ctx.get("phone") or None, simulate=not config.WHATSAPP_ENABLED)
    return {"appointment_booked": True, "appointment_details": appt, "trace": ["appointment_booking"]}


# ---------------------------------------------------------------- Agent 11: Report Delivery
def report_delivery_agent(state: NoveraState) -> dict[str, Any]:
    ctx = state.get("user_context", {})
    lang = _lang(state)
    path = state.get("report_path", "")
    if lang == "ar":
        body = f"📄 إليك تقرير فحص نوفيرا الكامل الخاص بك.\n{DISCLAIMER}"
    else:
        body = f"📄 Here is your full Novera screening report.\n{DISCLAIMER}"
    # WhatsApp document send is wired at the API-key step; we send the notice + attach path in simulate.
    whatsapp.send_message(f"{body}\n[document: {path}]", to=ctx.get("phone") or None, simulate=not config.WHATSAPP_ENABLED)
    return {"trace": ["report_delivery"]}
