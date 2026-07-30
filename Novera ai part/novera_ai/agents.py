"""Content + analysis agents. Each returns a plain dict and always succeeds,
falling back to deterministic bilingual output if the LLM is unavailable."""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from . import fallbacks
from .llm import LLMError, structured_json_call
from .schemas import ChatOut, ReportOut, SelfCareOut, VoiceOut

REFERENCE_LABELS = fallbacks.REFERENCE_LABELS
METRIC_KEYS = fallbacks.METRIC_KEYS


def _lang_name(lang: str) -> str:
    return "Arabic" if lang == "ar" else "English"


def _describe_reading(reading: dict[str, Any]) -> str:
    lines = []
    for k in METRIC_KEYS:
        m = reading["metrics"][k]
        unit = f" {m['unit']}" if m.get("unit") else ""
        rng = m["range"]
        lines.append(f"- {REFERENCE_LABELS[k]}: {m['value']}{unit} (reference {rng[0]}-{rng[1]}, status: {m['status']})")
    areas = ", ".join(f"{a}: {s}" for a, s in reading["healthAreas"].items())
    return f"Reading timestamp: {reading['timestamp']}\nBiomarkers:\n" + "\n".join(lines) + f"\nHealth areas — {areas}"


def _describe_context(ctx: dict[str, Any]) -> str:
    if not ctx or not (ctx.get("diagnosis") or ctx.get("medications") or ctx.get("notes")):
        return "No doctor-provided context has been shared yet."
    parts = []
    if ctx.get("diagnosis"):
        parts.append(f"Doctor's diagnosis: {ctx['diagnosis']}")
    if ctx.get("medications"):
        parts.append(f"Medications: {ctx['medications']}")
    if ctx.get("notes"):
        parts.append(f"Other notes: {ctx['notes']}")
    return "\n".join(parts)


# ---------------------------------------------------------------- voice
def voice_agent(reading: dict[str, Any], lang: str = "en") -> dict[str, Any]:
    try:
        out = structured_json_call(
            system=(
                f"You are NOVERA's Guidance Agent. Write a spoken screening SUMMARY (not a diagnosis) "
                f"to be read aloud by a text-to-speech voice, entirely in {_lang_name(lang)}. Warm, clear, "
                f"5-8 flowing sentences, no markdown or bullets. Always note it is research-stage, not medical advice."
            ),
            user=f"Compose the spoken summary from this reading:\n{_describe_reading(reading)}",
            model_cls=VoiceOut,
            max_tokens=900,
        )
        return {"script": out.script, "source": "ai"}
    except LLMError as exc:
        print(f"[voice] fallback: {exc}")
        return fallbacks.voice(reading, lang)


# ---------------------------------------------------------------- report
def report_agent(reading: dict[str, Any], ctx: dict[str, Any], lang: str = "en") -> dict[str, Any]:
    try:
        out = structured_json_call(
            system=(
                f"You are NOVERA's Insight Agent producing a plain-language screening report in {_lang_name(lang)}. "
                f"It is a screening summary, NOT a diagnosis. Cover all four health areas using these exact ids: "
                f"kidney, hydration, oral, digestive. If the patient shared doctor context, take it into account gently. "
                f"Keep each area note 1-2 sentences."
            ),
            user=f"{_describe_reading(reading)}\n\nPatient context:\n{_describe_context(ctx)}",
            model_cls=ReportOut,
            max_tokens=1400,
        )
        data = out.model_dump()
        data["disclaimer"] = fallbacks.RESEARCH_LINE.get(lang, fallbacks.RESEARCH_LINE["en"])
        data["source"] = "ai"
        return data
    except LLMError as exc:
        print(f"[report] fallback: {exc}")
        return fallbacks.report(reading, lang)


# ---------------------------------------------------------------- self-care
def self_care_agent(reading: dict[str, Any], ctx: dict[str, Any], chat_history: list[dict[str, Any]], lang: str = "en") -> dict[str, Any]:
    convo = "\n".join(
        f"{'Patient' if m['role'] == 'user' else 'Assistant'}: {m['content']}" for m in (chat_history or [])
    )
    try:
        out = structured_json_call(
            system=(
                f"You are NOVERA's Guidance Agent, a supportive wellness coach writing in {_lang_name(lang)}. "
                f"Produce a practical, personalised diet plan and self-care guidance from the saliva screening, the "
                f"doctor's context, and the conversation. General wellness guidance, not medical treatment. Respect any "
                f"diagnosis/medications (e.g. if kidney-related, favour kidney-friendly, lower-sodium, protein-moderate "
                f"choices). Keep meals concrete and simple. Use area ids: kidney, hydration, oral, digestive. "
                f"ALSO include a 'nutrition' list with one entry per meal (breakfast, lunch, dinner, snacks) giving "
                f"realistic estimated calories, protein_g, carbs_g, fat_g, and 1-3 short 'micros' highlights "
                f"(e.g. 'High in potassium', 'Rich in omega-3'). Meal descriptions and micros must be in "
                f"{_lang_name(lang)}."
            ),
            user=(
                f"{_describe_reading(reading)}\n\nPatient context:\n{_describe_context(ctx)}\n\n"
                f"Conversation so far:\n{convo or '(none)'}\n\n"
                f"Produce today's focus, a full diet plan (breakfast/lunch/dinner/snacks/hydration), one tip per health "
                f"area, and the nutrition breakdown for breakfast, lunch, dinner and snacks."
            ),
            model_cls=SelfCareOut,
            max_tokens=2200,
            temperature=0.4,
        )
        data = out.model_dump()
        data["source"] = "ai"
        # Free models sometimes omit the nutrition block — backfill it so the
        # meal timeline always has macros.
        if not data.get("nutrition"):
            data["nutrition"] = fallbacks.self_care(reading, lang)["nutrition"]
        return data
    except LLMError as exc:
        print(f"[self_care] fallback: {exc}")
        return fallbacks.self_care(reading, lang)


# ---------------------------------------------------------------- chat
def chat_agent(messages: list[dict[str, Any]], reading: dict[str, Any] | None, ctx: dict[str, Any], lang: str = "en") -> dict[str, Any]:
    convo = "\n".join(f"{'Patient' if m['role'] == 'user' else 'Assistant'}: {m['content']}" for m in messages)
    reading_txt = _describe_reading(reading) if reading else "No reading available."
    try:
        out = structured_json_call(
            system=(
                f"You are NOVERA's Guidance Agent chatting with a patient in {_lang_name(lang)}. The patient tells you "
                f"what their doctor said — diagnosis, medications, instructions. Be warm and concise (2-4 sentences), and "
                f"ask a gentle follow-up when useful. MAINTAIN a running structured record: return the FULL updated "
                f"diagnosis / medications / notes (merge new info with prior — never lose earlier info). Set contextChanged "
                f"true only if you added or changed something. Never give a medical diagnosis yourself. The reply must be in "
                f"{_lang_name(lang)}, but keep diagnosis/medications/notes in concise English."
            ),
            user=(
                f"Current stored context:\nDiagnosis: {ctx.get('diagnosis') or '(none)'}\n"
                f"Medications: {ctx.get('medications') or '(none)'}\nNotes: {ctx.get('notes') or '(none)'}\n\n"
                f"Latest reading: {reading_txt}\n\nConversation:\n{convo}\n\n"
                f"Respond to the patient's last message and return the updated context record."
            ),
            model_cls=ChatOut,
            max_tokens=900,
            temperature=0.4,
        )
        data = out.model_dump()
        data["source"] = "ai"
        return data
    except LLMError as exc:
        print(f"[chat] fallback: {exc}")
        return fallbacks.chat(messages, ctx, lang)


# ---------------------------------------------------------------- organ prediction (reuses novera.py core)
CREATININE_MGDL_TO_UMOLL = 88.42


@lru_cache(maxsize=1)
def _organ_core():
    """Lazily build the deterministic scoring engine from the existing core."""
    import novera  # the original CLI module (well-structured pipeline)

    db = novera.Database(novera.DATABASE_PATH)
    db.initialize()
    ranges = db.load_reference_ranges()
    engine = novera.ScoringEngine(db, ranges, novera.CONFIRMED_CASE_QUERY_LIMIT)
    return novera, engine


class _OrganDecision:  # small pydantic-free schema for structured_json_call
    pass


def predict_organ(reading: dict[str, Any]) -> dict[str, Any]:
    """Predict the most likely affected organ (KIDNEY/STOMACH/ORAL) from a web reading.

    Uses the deterministic specialist scoring from novera.py, then one LLM call
    for the final decision, falling back to the deterministic leader.
    """
    from pydantic import BaseModel, Field

    novera, engine = _organ_core()
    m = reading["metrics"]
    values = {
        "ph": float(m["ph"]["value"]),
        "urea_mg_dl": float(m["urea"]["value"]),
        "creatinine_umol_l": float(m["creatinine"]["value"]) * CREATININE_MGDL_TO_UMOLL,
        "temperature_c": float(m["temperature"]["value"]),
    }
    specialist = [engine.evaluate(o, values) for o in novera.ORGANS]
    ranked = sorted(specialist, key=lambda r: r["combined_score"], reverse=True)
    leader = ranked[0]["organ"]

    compact = [
        {k: r[k] for k in ("organ", "range_score", "similarity_score", "combined_score", "flag")}
        for r in specialist
    ]

    class OrganDecision(BaseModel):
        prediction: str = Field(pattern="^(KIDNEY|STOMACH|ORAL)$")
        confidence: float = Field(ge=0.0, le=1.0)
        reason: str = Field(min_length=10, max_length=500)

    try:
        out = structured_json_call(
            system=(
                "You are NOVERA's final organ-screening decision component. Choose exactly one: KIDNEY, STOMACH, or ORAL, "
                "based only on the supplied specialist scores. Never invent thresholds. The reason must mention the range "
                "and similarity scores that drove the choice. This is experimental screening support, not a diagnosis."
            ),
            user=json.dumps(
                {"deterministic_leader": leader, "specialist_results": compact, "values": values},
                ensure_ascii=False,
            ),
            model_cls=OrganDecision,
            max_tokens=500,
            temperature=0.0,
        )
        decision = out.model_dump()
        decision["prediction"] = decision["prediction"].upper()
        decision["source"] = "ai"
    except LLMError as exc:
        print(f"[predict_organ] fallback: {exc}")
        decision = {
            "prediction": leader,
            "confidence": round(float(ranked[0]["combined_score"]), 3),
            "reason": (
                f"Deterministic specialist scoring ranked {leader} highest "
                f"(combined score {ranked[0]['combined_score']})."
            ),
            "source": "fallback",
        }

    return {**decision, "specialist_results": specialist}
