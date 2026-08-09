"""The screening pipeline's single OpenRouter decision call (req 5, 8, 17).

Ported from novera.py's OpenRouterDecisionMaker + NoveraService pipeline.
Kept as plain sequential Python (fetch -> validate -> score -> decide ->
persist/release) rather than a LangGraph state machine — it's a strictly
linear flow with no branching worth the extra machinery; LangGraph is used
where this project actually needs it: the WhatsApp appointment conversation
(core/appointment_graph.py, core/whatsapp_agent.py).
"""
from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import ValidationError

from .. import config
from ..schemas import FinalDecision
from . import scoring


class OpenRouterDecisionError(RuntimeError):
    """Raised when OpenRouter does not produce a valid single-organ decision."""


def _extract_tool_arguments(response: Any) -> dict[str, Any]:
    tool_calls = getattr(response, "tool_calls", None) or []
    for call in tool_calls:
        if str(call.get("name", "")) == "FinalDecision":
            args = call.get("args", {})
            if isinstance(args, dict):
                return args

    additional = getattr(response, "additional_kwargs", {}) or {}
    for call in additional.get("tool_calls") or []:
        function = call.get("function") or {}
        if function.get("name") != "FinalDecision":
            continue
        raw_args = function.get("arguments", "{}")
        if isinstance(raw_args, dict):
            return raw_args
        try:
            parsed = json.loads(raw_args)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict):
            return parsed

    raise OpenRouterDecisionError("OpenRouter did not return the required decision structure.")


def decide(reading: dict[str, Any], specialist_results: list[dict[str, Any]]) -> tuple[dict[str, Any], str, dict[str, Any]]:
    """Exactly one OpenRouter call, forced to return a single KIDNEY/STOMACH/ORAL decision."""
    if not config.AI_ENABLED:
        raise OpenRouterDecisionError("A valid OPENROUTER_API_KEY is not configured.")

    model = config.OPENROUTER_MODEL_SCREENING

    compact_results = [
        {k: item[k] for k in ("organ", "range_score", "similarity_score", "combined_score", "matched_cases", "flag", "closest_confirmed_cases")}
        for item in specialist_results
    ]

    llm = ChatOpenAI(
        model=model,
        api_key=config.OPENROUTER_API_KEY,
        base_url=config.OPENROUTER_BASE_URL,
        temperature=0,
        timeout=config.OPENROUTER_TIMEOUT_SECONDS,
        max_retries=0,
        default_headers={"HTTP-Referer": "http://localhost", "X-Title": "NOVERA Screening Core"},
    )
    decision_llm = llm.bind_tools([FinalDecision], tool_choice="FinalDecision", parallel_tool_calls=False)

    ranked = sorted(compact_results, key=lambda item: item["combined_score"], reverse=True)
    deterministic_leader = ranked[0]["organ"]

    messages = [
        SystemMessage(content=(
            "You are the NOVERA final screening decision component. This is experimental "
            "screening support, not a confirmed diagnosis. The Kidney, Stomach, and Oral "
            "specialist results were calculated before this call using project reference "
            "ranges and limited human-confirmed SQL memory. Make exactly one final "
            "prediction: KIDNEY, STOMACH, or ORAL. Never output MULTIPLE, NO_CLEAR_PATTERN, "
            "or any other label. Use only the supplied evidence. The reason must mention the "
            "range score, similarity score, and confirmed-case support that drove the choice. "
            "Do not invent medical thresholds, diagnoses, or historical cases."
        )),
        HumanMessage(content=json.dumps(
            {
                "case_id": reading["case_id"],
                "values": {key: reading[key] for key in scoring.BIOMARKERS},
                "deterministic_leader": deterministic_leader,
                "specialist_results": compact_results,
            },
            ensure_ascii=False,
        )),
    ]

    try:
        response = decision_llm.invoke(messages)  # <-- the one and only LLM call
        arguments = _extract_tool_arguments(response)
        validated = FinalDecision.model_validate(arguments)
    except (OpenRouterDecisionError, ValidationError) as exc:
        raise OpenRouterDecisionError("OpenRouter did not return a valid single-organ decision.") from exc
    except Exception as exc:
        raise OpenRouterDecisionError("OpenRouter could not complete the decision.") from exc

    decision = validated.model_dump()
    decision["prediction"] = str(decision["prediction"]).upper()
    decision["confidence"] = round(float(decision["confidence"]), 4)
    decision["reason"] = str(decision["reason"]).strip()
    if decision["prediction"] not in scoring.ORGANS:
        raise OpenRouterDecisionError("OpenRouter returned an unsupported prediction.")
    if not decision["reason"]:
        raise OpenRouterDecisionError("OpenRouter returned no explanation.")

    response_metadata = getattr(response, "response_metadata", {}) or {}
    actual_model = str(response_metadata.get("model_name") or response_metadata.get("model") or model)
    raw_result = {"prediction": decision["prediction"], "confidence": decision["confidence"], "reason": decision["reason"]}
    return decision, actual_model, raw_result


def process_case_stream(reading: dict[str, Any]):
    """Same pipeline as process_case, but a generator: yields one event after
    each real step actually completes (validate, score per organ, decide,
    persist/release), for a workflow visualizer driven by real backend
    progress rather than a decorative timer. The last event is always
    {"step": "done", "status": ..., "result": ...} carrying exactly what
    process_case() used to return directly.

    On any OpenRouter failure the case is released back to NEW with no saved
    prediction and no invented reason (req 8) — the caller sees RETRY_REQUIRED.
    """
    errors = scoring.validate_reading(reading)
    if errors:
        reason = "; ".join(errors)
        yield {"step": "validate", "status": "failed", "detail": reason}
        scoring.mark_retest_required(reading["id"], reason)
        yield {
            "step": "done",
            "status": "failed",
            "result": {"status": "RETEST_REQUIRED", "case_id": reading["case_id"], "reason": reason},
        }
        return
    yield {"step": "validate", "status": "passed"}

    values = {biomarker: float(reading[biomarker]) for biomarker in scoring.BIOMARKERS}
    engine = scoring.get_engine()
    specialist_results = []
    for organ in scoring.ORGANS:
        result = engine.evaluate(organ, values)
        specialist_results.append(result)
        yield {
            "step": f"score:{organ}",
            "status": "passed",
            "detail": {"combined_score": result["combined_score"], "flag": result["flag"]},
        }

    yield {"step": "decide", "status": "running"}
    try:
        decision, model, raw_result = decide(reading, specialist_results)
    except OpenRouterDecisionError:
        scoring.release_reading(reading["id"])
        yield {"step": "decide", "status": "failed"}
        yield {
            "step": "done",
            "status": "failed",
            "result": {
                "status": "RETRY_REQUIRED",
                "case_id": reading["case_id"],
                "message": "The AI decision was not saved. The case remains NEW; check the OpenRouter key/model access and try again.",
            },
        }
        return
    yield {
        "step": "decide",
        "status": "passed",
        "detail": {"prediction": decision["prediction"], "confidence": decision["confidence"]},
    }

    scoring.persist_decision(reading, decision, specialist_results, model, raw_result)
    yield {"step": "persist", "status": "passed"}
    yield {
        "step": "done",
        "status": "passed",
        "result": {
            "status": "PROCESSED",
            "case_id": reading["case_id"],
            "ai_prediction": decision["prediction"],
            "ai_confidence": decision["confidence"],
            "ai_reason": decision["reason"],
            "specialist_results": specialist_results,
        },
    }


def process_case(reading: dict[str, Any]) -> dict[str, Any]:
    """Full pipeline for one screening case: validate -> score -> decide -> persist/release.

    Thin wrapper over process_case_stream() for callers that only want the
    final result — unchanged behavior/signature for existing callers.
    """
    final_result: dict[str, Any] | None = None
    for event in process_case_stream(reading):
        if event["step"] == "done":
            final_result = event["result"]
    assert final_result is not None, "process_case_stream must always yield a final 'done' event"
    return final_result


def process_latest() -> dict[str, Any]:
    reading = scoring.fetch_latest_new_reading()
    if reading is None:
        return {"status": "NO_NEW_CASE"}
    if not scoring.claim_reading(reading["id"]):
        return {"status": "CASE_ALREADY_PROCESSING"}
    reading["status"] = "PROCESSING"
    return process_case(reading)
