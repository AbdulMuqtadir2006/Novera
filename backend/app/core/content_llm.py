"""Content agents — voice / report / self-care / chat.

Each makes exactly one OpenRouter call (via ChatOpenAI) and always succeeds,
falling back to deterministic bilingual output (fallbacks.py) if the LLM is
unavailable or returns something that doesn't validate. Ported from the old
novera_ai/agents.py + novera_ai/llm.py.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Type, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ValidationError

from .. import config, db
from ..schemas import ReportOut, SelfCareOut, VoiceOut
from . import fallbacks, reference_data

REFERENCE_LABELS = fallbacks.REFERENCE_LABELS
METRIC_KEYS = fallbacks.METRIC_KEYS

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


def _make_llm(temperature: float = 0.3, max_tokens: int = 1200) -> ChatOpenAI:
    if not config.AI_ENABLED:
        raise LLMError("OPENROUTER_API_KEY not configured (must start with sk-or-).")
    return ChatOpenAI(
        model=config.OPENROUTER_MODEL_CONTENT,
        api_key=config.OPENROUTER_API_KEY,
        base_url=config.OPENROUTER_BASE_URL,
        temperature=temperature,
        timeout=config.OPENROUTER_TIMEOUT_SECONDS,
        max_retries=1,
        max_tokens=max_tokens,
        default_headers={"HTTP-Referer": "http://localhost", "X-Title": "NOVERA Agentic Core"},
    )


def _extract_json(text: str) -> dict:
    if not text:
        raise LLMError("Empty model response.")
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise LLMError("No JSON object found in model response.")
        candidate = text[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise LLMError(f"Model returned invalid JSON: {exc}") from exc


def structured_json_call(system: str, user: str, model_cls: Type[T], temperature: float = 0.3, max_tokens: int = 1400) -> T:
    schema = json.dumps(model_cls.model_json_schema(), ensure_ascii=False)
    full_system = (
        f"{system}\n\nRespond with ONE valid JSON object only — no prose, no markdown, no code "
        f"fences. It must match this JSON schema (keys and types):\n{schema}"
    )
    llm = _make_llm(temperature=temperature, max_tokens=max_tokens)
    try:
        response = llm.invoke([{"role": "system", "content": full_system}, {"role": "user", "content": user}])
    except Exception as exc:
        raise LLMError(f"LLM call failed: {exc}") from exc

    data = _extract_json(str(response.content))
    try:
        return model_cls.model_validate(data)
    except ValidationError as exc:
        raise LLMError(f"Model output failed validation: {exc}") from exc


def agentic_structured_call(
    system: str,
    user: str,
    model_cls: Type[T],
    tools: list | None = None,
    temperature: float = 0.3,
    max_tokens: int = 1400,
    max_iterations: int = 3,
) -> T:
    """Like structured_json_call, but the model may optionally call read-only
    `tools` (fetch its own extra context) before producing its final JSON
    answer — a minimal agentic loop for content agents that benefit from
    pulling context the caller didn't already hand them, rather than only
    ever seeing what was pre-fetched. Same failure contract as
    structured_json_call: any failure (LLM error, no final answer within
    max_iterations, invalid JSON, schema validation failure) raises
    LLMError, which callers already turn into the deterministic fallback —
    an unresolved tool loop never fabricates a result."""
    schema = json.dumps(model_cls.model_json_schema(), ensure_ascii=False)
    full_system = (
        f"{system}\n\nWhen you are ready to answer, respond with ONE valid JSON object only — "
        f"no prose, no markdown, no code fences — matching this JSON schema (keys and types):\n{schema}"
    )
    llm = _make_llm(temperature=temperature, max_tokens=max_tokens)
    tool_map = {t.name: t for t in (tools or [])}
    if tools:
        llm = llm.bind_tools(tools)

    messages: list = [SystemMessage(content=full_system), HumanMessage(content=user)]
    for _ in range(max_iterations):
        try:
            response = llm.invoke(messages)
        except Exception as exc:
            raise LLMError(f"LLM call failed: {exc}") from exc
        messages.append(response)
        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            data = _extract_json(str(response.content))
            try:
                return model_cls.model_validate(data)
            except ValidationError as exc:
                raise LLMError(f"Model output failed validation: {exc}") from exc
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
                    result_text = f"Tool {name} raised an error: {exc}"
            messages.append(ToolMessage(content=str(result_text), tool_call_id=call_id))
    raise LLMError(f"Agentic call did not reach a final answer within {max_iterations} iterations.")


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


def _describe_history(history: list[dict[str, Any]]) -> str:
    if not history:
        return "No earlier readings available — this is the only reading on file."
    lines = [
        "- " + ", ".join(f"{k}={r['metrics'][k]['value']}" for k in METRIC_KEYS) + f" ({r['timestamp']})"
        for r in history
    ]
    return "Past readings, oldest first:\n" + "\n".join(lines)


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


def report_agent(reading: dict[str, Any], ctx: dict[str, Any], lang: str = "en") -> dict[str, Any]:
    @tool
    def get_reading_history(days: int = 30) -> str:
        """Look up this patient's past biomarker readings (oldest to newest) to check
        whether a value has been trending, before writing the report. `days` controls
        how far back to look (default 30). Optional — only call this if a trend would
        actually change what's worth telling the patient (e.g. a borderline value that's
        been climbing); don't call it if the latest reading alone is enough."""
        return _describe_history(reference_data.get_reading_history(days))

    try:
        out = agentic_structured_call(
            system=(
                f"You are NOVERA's Insight Agent producing a plain-language screening report in {_lang_name(lang)}. "
                f"It is a screening summary, NOT a diagnosis. Cover all four health areas using these exact ids: "
                f"kidney, hydration, oral, digestive. If the patient shared doctor context, take it into account gently. "
                f"Keep each area note 1-2 sentences."
            ),
            user=f"{_describe_reading(reading)}\n\nPatient context:\n{_describe_context(ctx)}",
            model_cls=ReportOut,
            tools=[get_reading_history],
            max_tokens=1400,
        )
        data = out.model_dump()
        data["disclaimer"] = fallbacks.RESEARCH_LINE.get(lang, fallbacks.RESEARCH_LINE["en"])
        data["source"] = "ai"
        return data
    except LLMError as exc:
        print(f"[report] fallback: {exc}")
        return fallbacks.report(reading, lang)


def _self_care_plan_exists() -> bool:
    row = db.fetch_one("SELECT plan_json FROM self_care_plan WHERE id = 1")
    return bool(row and row.get("plan_json"))


def _persist_self_care_plan(data: dict[str, Any]) -> None:
    db.execute(
        "UPDATE self_care_plan SET plan_json = %s, updated_at = now() WHERE id = 1",
        (json.dumps(data, ensure_ascii=False),),
    )


def self_care_agent(reading: dict[str, Any], ctx: dict[str, Any], chat_history: list[dict[str, Any]], lang: str = "en") -> dict[str, Any]:
    convo = "\n".join(f"{'Patient' if m['role'] == 'user' else 'Assistant'}: {m['content']}" for m in (chat_history or []))
    try:
        out = structured_json_call(
            system=(
                f"You are NOVERA's Guidance Agent, a supportive wellness coach writing in {_lang_name(lang)}. "
                f"Produce a practical, personalised diet plan and self-care guidance from the saliva screening, the "
                f"doctor's context, and the conversation. General wellness guidance, not medical treatment. Respect any "
                f"diagnosis/medications (e.g. if kidney-related, favour kidney-friendly, lower-sodium, protein-moderate "
                f"choices). Keep meals concrete and simple. Use area ids: kidney, hydration, oral, digestive. "
                f"ALSO include a 'nutrition' list with one entry per meal (breakfast, lunch, dinner, snacks) giving "
                f"realistic estimated calories, protein_g, carbs_g, fat_g, and 1-3 short 'micros' highlights. Meal "
                f"descriptions and micros must be in {_lang_name(lang)}."
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
        if not data.get("nutrition"):
            data["nutrition"] = fallbacks.self_care(reading, lang)["nutrition"]
        _persist_self_care_plan(data)
        return data
    except LLMError as exc:
        print(f"[self_care] fallback: {exc}")
        data = fallbacks.self_care(reading, lang)
        # Don't clobber a plan the patient may be actively editing via chat
        # with a degraded fallback — only persist if nothing was ever saved.
        if not _self_care_plan_exists():
            _persist_self_care_plan(data)
        return data


# ---------------------------------------------------------------------------
# Chat coach — real tool-calling agent (guidance_agent.py-shaped: a ChatOpenAI
# bound to tools, a manual invoke -> tool_calls -> ToolMessage -> invoke loop,
# terminating on a plain-text final reply rather than forced JSON, since a
# chat reply is free text, not a fixed schema).
# ---------------------------------------------------------------------------
DIET_PLAN_FIELDS = {"breakfast", "lunch", "dinner", "snacks", "hydration"}
CONTEXT_FIELDS = {"diagnosis", "medications", "notes"}

# Small curated dataset — deliberately NOT an external API call (no new
# credentials). Rough calories/protein/carbs/fat per a typical serving.
FOOD_NUTRITION_DB: dict[str, dict[str, Any]] = {
    "oats": {"serving": "1/2 cup dry", "calories": 150, "protein_g": 5, "carbs_g": 27, "fat_g": 3},
    "brown rice": {"serving": "1 cup cooked", "calories": 216, "protein_g": 5, "carbs_g": 45, "fat_g": 2},
    "white rice": {"serving": "1 cup cooked", "calories": 205, "protein_g": 4, "carbs_g": 45, "fat_g": 0},
    "lentils": {"serving": "1 cup cooked", "calories": 230, "protein_g": 18, "carbs_g": 40, "fat_g": 1},
    "chickpeas": {"serving": "1 cup cooked", "calories": 269, "protein_g": 15, "carbs_g": 45, "fat_g": 4},
    "black beans": {"serving": "1 cup cooked", "calories": 227, "protein_g": 15, "carbs_g": 41, "fat_g": 1},
    "salmon": {"serving": "100g cooked", "calories": 208, "protein_g": 20, "carbs_g": 0, "fat_g": 13},
    "tuna": {"serving": "100g canned in water", "calories": 116, "protein_g": 26, "carbs_g": 0, "fat_g": 1},
    "shrimp": {"serving": "100g cooked", "calories": 99, "protein_g": 24, "carbs_g": 0, "fat_g": 1},
    "chicken breast": {"serving": "100g cooked", "calories": 165, "protein_g": 31, "carbs_g": 0, "fat_g": 4},
    "turkey breast": {"serving": "100g cooked", "calories": 135, "protein_g": 30, "carbs_g": 0, "fat_g": 1},
    "eggs": {"serving": "1 large", "calories": 78, "protein_g": 6, "carbs_g": 1, "fat_g": 5},
    "tofu": {"serving": "100g", "calories": 76, "protein_g": 8, "carbs_g": 2, "fat_g": 5},
    "spinach": {"serving": "1 cup raw", "calories": 7, "protein_g": 1, "carbs_g": 1, "fat_g": 0},
    "kale": {"serving": "1 cup raw", "calories": 33, "protein_g": 2, "carbs_g": 6, "fat_g": 0},
    "broccoli": {"serving": "1 cup cooked", "calories": 55, "protein_g": 4, "carbs_g": 11, "fat_g": 1},
    "carrots": {"serving": "1 cup raw", "calories": 52, "protein_g": 1, "carbs_g": 12, "fat_g": 0},
    "cucumber": {"serving": "1 cup sliced", "calories": 16, "protein_g": 1, "carbs_g": 4, "fat_g": 0},
    "tomato": {"serving": "1 medium", "calories": 22, "protein_g": 1, "carbs_g": 5, "fat_g": 0},
    "sweet potato": {"serving": "1 medium baked", "calories": 103, "protein_g": 2, "carbs_g": 24, "fat_g": 0},
    "potato": {"serving": "1 medium baked", "calories": 161, "protein_g": 4, "carbs_g": 37, "fat_g": 0},
    "quinoa": {"serving": "1 cup cooked", "calories": 222, "protein_g": 8, "carbs_g": 39, "fat_g": 4},
    "whole wheat bread": {"serving": "1 slice", "calories": 81, "protein_g": 4, "carbs_g": 14, "fat_g": 1},
    "banana": {"serving": "1 medium", "calories": 105, "protein_g": 1, "carbs_g": 27, "fat_g": 0},
    "apple": {"serving": "1 medium", "calories": 95, "protein_g": 0, "carbs_g": 25, "fat_g": 0},
    "orange": {"serving": "1 medium", "calories": 62, "protein_g": 1, "carbs_g": 15, "fat_g": 0},
    "blueberries": {"serving": "1 cup", "calories": 84, "protein_g": 1, "carbs_g": 21, "fat_g": 0},
    "watermelon": {"serving": "1 cup diced", "calories": 46, "protein_g": 1, "carbs_g": 12, "fat_g": 0},
    "dates": {"serving": "2 dates", "calories": 133, "protein_g": 1, "carbs_g": 36, "fat_g": 0},
    "almonds": {"serving": "1 oz (~23 nuts)", "calories": 164, "protein_g": 6, "carbs_g": 6, "fat_g": 14},
    "walnuts": {"serving": "1 oz (~14 halves)", "calories": 185, "protein_g": 4, "carbs_g": 4, "fat_g": 18},
    "cashews": {"serving": "1 oz (~18 nuts)", "calories": 157, "protein_g": 5, "carbs_g": 9, "fat_g": 12},
    "peanut butter": {"serving": "2 tbsp", "calories": 190, "protein_g": 7, "carbs_g": 7, "fat_g": 16},
    "greek yogurt": {"serving": "170g plain, nonfat", "calories": 100, "protein_g": 17, "carbs_g": 6, "fat_g": 1},
    "yogurt": {"serving": "170g plain, low-fat", "calories": 140, "protein_g": 12, "carbs_g": 16, "fat_g": 4},
    "milk": {"serving": "1 cup low-fat", "calories": 102, "protein_g": 8, "carbs_g": 12, "fat_g": 2},
    "cottage cheese": {"serving": "1/2 cup, low-fat", "calories": 90, "protein_g": 12, "carbs_g": 5, "fat_g": 2},
    "cheddar cheese": {"serving": "1 oz", "calories": 113, "protein_g": 7, "carbs_g": 0, "fat_g": 9},
    "avocado": {"serving": "1/2 fruit", "calories": 160, "protein_g": 2, "carbs_g": 9, "fat_g": 15},
    "olive oil": {"serving": "1 tbsp", "calories": 119, "protein_g": 0, "carbs_g": 0, "fat_g": 14},
    "honey": {"serving": "1 tbsp", "calories": 64, "protein_g": 0, "carbs_g": 17, "fat_g": 0},
    "popcorn": {"serving": "3 cups air-popped", "calories": 93, "protein_g": 3, "carbs_g": 19, "fat_g": 1},
}

# Lightweight, rule-based (NOT another LLM call) — keyword in the patient's
# stated concern -> a short list of foods commonly flagged for it.
DIETARY_CONFLICT_RULES: dict[str, dict[str, Any]] = {
    "kidney": {
        "foods": ["banana", "orange", "potato", "tomato", "dairy", "milk", "cheese", "nuts", "almonds",
                   "cashews", "beans", "lentils", "chocolate", "avocado", "dates"],
        "note": "it's relatively high in potassium/phosphorus, which kidney-related diets often need to limit — check with a doctor about safe portions.",
    },
    "sodium": {
        "foods": ["processed meat", "canned soup", "pickles", "soy sauce", "cheese", "salted nuts",
                   "chips", "bacon", "deli meat", "instant noodles", "popcorn"],
        "note": "it's typically high in sodium, which a low-sodium diet usually needs to limit.",
    },
    "diabet": {
        "foods": ["white rice", "white bread", "honey", "dates", "watermelon", "soda", "pastries",
                   "candy", "juice", "sugar"],
        "note": "it's high in fast-digesting carbs/sugar, which can spike blood sugar — portion and pairing with protein/fibre matters.",
    },
    "blood sugar": {
        "foods": ["white rice", "white bread", "honey", "dates", "watermelon", "soda", "pastries",
                   "candy", "juice", "sugar"],
        "note": "it's high in fast-digesting carbs/sugar, which can spike blood sugar — portion and pairing with protein/fibre matters.",
    },
    "cholesterol": {
        "foods": ["red meat", "bacon", "butter", "cheese", "fried", "cream", "egg yolk"],
        "note": "it's higher in saturated fat, which a cholesterol-conscious diet often limits.",
    },
}


def _persist_context_update(diagnosis: str, medications: str, notes: str) -> None:
    db.execute(
        "UPDATE patient_context SET diagnosis = %s, medications = %s, notes = %s, updated_at = %s WHERE id = 1",
        (diagnosis, medications, notes, datetime.now(timezone.utc)),
    )


def _merge_context_field(existing: str, new_value: str) -> str:
    existing = (existing or "").strip()
    new_value = (new_value or "").strip()
    if not new_value:
        return existing
    if not existing:
        return new_value
    if new_value.lower() in existing.lower():
        return existing  # already recorded, don't duplicate
    return f"{existing}; {new_value}"


def _build_chat_tools(flags: dict[str, bool]) -> list:
    @tool
    def update_diet_plan_field(meal: str, new_text: str) -> str:
        """Apply a targeted edit to ONE meal/section of the patient's saved diet
        plan. `meal` must be one of: breakfast, lunch, dinner, snacks, hydration.
        `new_text` is the full replacement text for that section. Call this once
        you've actually decided on a concrete swap (optionally after checking
        lookup_food_nutrition / check_dietary_conflict) — this is what makes the
        change show up for the patient, just describing it in the chat reply
        does not."""
        meal_key = (meal or "").strip().lower()
        if meal_key not in DIET_PLAN_FIELDS:
            return f"Unknown meal '{meal}'. Must be one of: {', '.join(sorted(DIET_PLAN_FIELDS))}."
        row = db.fetch_one("SELECT plan_json FROM self_care_plan WHERE id = 1")
        plan = row.get("plan_json") if row else None
        if isinstance(plan, str):
            plan = json.loads(plan)
        if not plan:
            return "No self-care plan exists yet — the patient needs to open the Self-Care page to generate one first."
        diet = dict(plan.get("dietPlan") or {})
        diet[meal_key] = new_text
        plan["dietPlan"] = diet
        db.execute(
            "UPDATE self_care_plan SET plan_json = %s, updated_at = now() WHERE id = 1",
            (json.dumps(plan, ensure_ascii=False),),
        )
        flags["plan_changed"] = True
        return f"Saved — {meal_key} is now: {new_text}"

    @tool
    def update_patient_context(field: str, value: str) -> str:
        """Save something the patient shared about their doctor's guidance —
        `field` is one of: diagnosis, medications, notes. `value` is the new
        information (concise English is fine regardless of chat language). This
        MERGES with whatever is already stored — it never overwrites or loses
        prior information. Call this whenever the patient reports something
        their doctor said, not just when they mention diet."""
        field_key = (field or "").strip().lower()
        if field_key not in CONTEXT_FIELDS:
            return f"Unknown field '{field}'. Must be one of: {', '.join(sorted(CONTEXT_FIELDS))}."
        current = reference_data.get_context()
        merged = _merge_context_field(current.get(field_key, ""), value)
        next_ctx = {
            "diagnosis": current.get("diagnosis", ""),
            "medications": current.get("medications", ""),
            "notes": current.get("notes", ""),
        }
        next_ctx[field_key] = merged
        _persist_context_update(next_ctx["diagnosis"], next_ctx["medications"], next_ctx["notes"])
        flags["context_changed"] = True
        return f"Saved — {field_key} is now: {merged}"

    @tool
    def lookup_food_nutrition(food_name: str) -> str:
        """Look up rough nutrition facts (calories, protein, carbs, fat per a
        typical serving) for a common food from NOVERA's small curated dataset
        (~40 everyday foods). If the food isn't in the dataset, says so honestly
        instead of guessing a number — you may still reason about it yourself
        using general knowledge, just don't present a fabricated figure as if it
        came from this tool."""
        key = (food_name or "").strip().lower()
        info = FOOD_NUTRITION_DB.get(key)
        if not info:
            return f"'{food_name}' is not in NOVERA's curated nutrition dataset — no verified figures available from this tool."
        return (
            f"{food_name.strip().title()} (per {info['serving']}): ~{info['calories']} kcal, "
            f"{info['protein_g']}g protein, {info['carbs_g']}g carbs, {info['fat_g']}g fat."
        )

    @tool
    def check_dietary_conflict(food_name: str, concern: str) -> str:
        """Lightweight rule-based check for whether `food_name` commonly
        conflicts with a stated dietary `concern` (e.g. "kidney", "low-sodium",
        "diabetic", "cholesterol"). Not a substitute for medical advice — a
        quick heuristic flag to inform a suggested swap."""
        concern_key = (concern or "").strip().lower()
        food_key = (food_name or "").strip().lower()
        rule = next((r for kw, r in DIETARY_CONFLICT_RULES.items() if kw in concern_key), None)
        if rule is None:
            return f"No specific rule for the concern '{concern}' in this lightweight checker — use general judgement."
        flagged = any(f in food_key or food_key in f for f in rule["foods"])
        if flagged:
            return f"Caution: {food_name} is commonly flagged for a '{concern}' concern — {rule['note']}"
        return f"No conflict found for {food_name} against a '{concern}' concern in this checker."

    return [update_diet_plan_field, update_patient_context, lookup_food_nutrition, check_dietary_conflict]


def chat_agent(messages: list[dict[str, Any]], reading: dict[str, Any] | None, ctx: dict[str, Any], lang: str = "en") -> dict[str, Any]:
    """NOVERA's chat coach — a real tool-calling agent (not a single structured
    call): it can make targeted, persisted edits (update_patient_context,
    update_diet_plan_field) using lookup_food_nutrition/check_dietary_conflict
    to reason about diet swaps, rather than only ever regenerating everything.
    Terminates on a plain-text reply (a chat message isn't a fixed schema).
    Same fallback discipline as the rest of this file: any failure (LLM not
    configured, network error, no final reply within the iteration cap) falls
    back to the deterministic fallbacks.chat(), tool-free."""
    convo = "\n".join(f"{'Patient' if m['role'] == 'user' else 'Assistant'}: {m['content']}" for m in messages)
    reading_txt = _describe_reading(reading) if reading else "No reading available."
    flags = {"context_changed": False, "plan_changed": False}
    tools = _build_chat_tools(flags)
    tool_map = {t.name: t for t in tools}

    system = (
        f"You are NOVERA's Guidance Agent chatting with a patient in {_lang_name(lang)}. Be warm and concise "
        f"(2-4 sentences), and ask a gentle follow-up when useful. Never give a medical diagnosis yourself — you are "
        f"a wellness coach, not a doctor.\n\n"
        "You have tools that make REAL, saved changes instead of just talking about them:\n"
        "- If the patient tells you what their doctor said (a diagnosis, medication, or instruction), call "
        "update_patient_context to save it — it merges with what's already stored, nothing is lost.\n"
        "- If the patient wants to swap or change a meal in their diet plan, use lookup_food_nutrition and/or "
        "check_dietary_conflict as needed to reason about the swap, then call update_diet_plan_field to actually "
        "apply it to their saved plan (don't just describe the change in words — apply it).\n"
        "- Not every message needs a tool call — if the patient is just chatting or asking a general question, "
        "reply directly.\n"
        f"Your final reply to the patient must be in {_lang_name(lang)}. Tool arguments and results can stay in "
        "English regardless of the chat language."
    )
    user = (
        f"Current stored context:\nDiagnosis: {ctx.get('diagnosis') or '(none)'}\n"
        f"Medications: {ctx.get('medications') or '(none)'}\nNotes: {ctx.get('notes') or '(none)'}\n\n"
        f"Latest reading: {reading_txt}\n\nConversation:\n{convo}\n\n"
        "Respond to the patient's last message, using tools if a targeted, saveable edit is actually warranted."
    )

    try:
        llm = _make_llm(temperature=0.4, max_tokens=900).bind_tools(tools)
        chat_messages: list = [SystemMessage(content=system), HumanMessage(content=user)]
        reply_text = None
        for _ in range(5):
            try:
                response = llm.invoke(chat_messages)
            except Exception as exc:
                raise LLMError(f"LLM call failed: {exc}") from exc
            chat_messages.append(response)
            tool_calls = getattr(response, "tool_calls", None) or []
            if not tool_calls:
                reply_text = str(response.content).strip()
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
                        result_text = f"Tool {name} raised an error: {exc}"
                chat_messages.append(ToolMessage(content=str(result_text), tool_call_id=call_id))
        if not reply_text:
            raise LLMError("Chat coach did not reach a final reply within the iteration cap.")
        return {
            "reply": reply_text,
            "source": "ai",
            "contextChanged": flags["context_changed"],
            "planChanged": flags["plan_changed"],
        }
    except LLMError as exc:
        print(f"[chat] fallback: {exc}")
        data = fallbacks.chat(messages, ctx, lang)
        if data.get("contextChanged"):
            _persist_context_update(data.get("diagnosis", ""), data.get("medications", ""), data.get("notes", ""))
        return {
            "reply": data["reply"],
            "source": data["source"],
            "contextChanged": bool(data.get("contextChanged")),
            "planChanged": False,
        }
