"""The screening pipeline's decision step (req 5, 8, 17).

Ported from novera.py's OpenRouterDecisionMaker + NoveraService pipeline.
Kept as plain sequential Python (fetch -> validate -> score -> decide ->
persist/release) rather than a LangGraph state machine — it's a strictly
linear flow with no branching worth the extra machinery; LangGraph is used
where this project actually needs it: the WhatsApp appointment conversation
(core/appointment_graph.py, core/whatsapp_agent.py).

`decide()` used to be exactly one forced OpenRouter call. It is now a small,
bounded tool-calling loop: the model can optionally look up the configured
reference ranges or re-run the confirmed-case similarity search before
committing, or explicitly escalate a genuinely ambiguous case for human
review instead of being forced to guess one of the three organs. All organ
scoring itself (range score, similarity score, combined score) still happens
entirely *before* decide() is ever called — see scoring.py and the callers'
score:{organ}/score_{organ} loops, both untouched by this change. decide()'s
external contract — decide(reading, specialist_results) -> (decision,
model_name, raw_result) on success, OpenRouterDecisionError on failure — is
unchanged; the new HumanReviewRequested exception is the one new signal
callers can act on.
"""
from __future__ import annotations

import json
import math
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import ValidationError

from .. import config
from ..schemas import FinalDecision
from . import scoring

MAX_ITERATIONS = 4


class OpenRouterDecisionError(RuntimeError):
    """Raised when OpenRouter does not produce a valid single-organ decision."""


class HumanReviewRequested(RuntimeError):
    """Raised when the model explicitly escalates a case instead of deciding.

    Callers should treat this the same way they treat a validation failure:
    route to scoring.mark_retest_required(reading_id, reason) rather than
    scoring.persist_decision()/release_reading() — never a silent fallback
    guess (req 8's no-fabrication guarantee applies here too).
    """

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _normalize_tool_calls(response: Any) -> list[dict[str, Any]]:
    """Normalize a ChatOpenAI response's tool calls to a flat list of
    {"name", "args", "id"} dicts, regardless of whether langchain_openai
    populated the normalized `.tool_calls` attribute or only the raw
    OpenAI-format `additional_kwargs.tool_calls` (some OpenRouter-routed
    models only reliably populate one or the other)."""
    calls = getattr(response, "tool_calls", None) or []
    normalized: list[dict[str, Any]] = []
    for call in calls:
        name = str(call.get("name", ""))
        args = call.get("args", {})
        if not isinstance(args, dict):
            args = {}
        normalized.append({"name": name, "args": args, "id": call.get("id") or name})
    if normalized:
        return normalized

    additional = getattr(response, "additional_kwargs", {}) or {}
    for call in additional.get("tool_calls") or []:
        function = call.get("function") or {}
        name = str(function.get("name", ""))
        raw_args = function.get("arguments", "{}")
        if isinstance(raw_args, dict):
            args = raw_args
        else:
            try:
                parsed = json.loads(raw_args)
            except (TypeError, json.JSONDecodeError):
                parsed = {}
            args = parsed if isinstance(parsed, dict) else {}
        normalized.append({"name": name, "args": args, "id": call.get("id") or name})
    return normalized


def _tool_get_organ_reference_ranges(organ: str) -> dict[str, Any]:
    organ = str(organ).upper()
    if organ not in scoring.ORGANS:
        return {"error": f"Unknown organ '{organ}'. Must be one of {list(scoring.ORGANS)}."}
    ranges = scoring.load_reference_ranges()
    return {
        "organ": organ,
        "ranges": {
            biomarker: {"min": spec.min_value, "max": spec.max_value, "weight": spec.weight}
            for biomarker, spec in ranges[organ].items()
        },
    }


def _tool_get_closest_confirmed_cases(reading: dict[str, Any], organ: str, limit: int) -> dict[str, Any]:
    """Re-run the same distance/similarity math ScoringEngine._similarity_score
    uses (kept in sync with it deliberately, not imported from it, since that
    method hardcodes top-3 and this tool's whole point is a caller-chosen
    result count) against a caller-specified number of closest confirmed
    cases, so the model can look deeper than the pre-computed top-3 already
    on specialist_results if it wants more evidence before deciding."""
    organ = str(organ).upper()
    if organ not in scoring.ORGANS:
        return {"error": f"Unknown organ '{organ}'. Must be one of {list(scoring.ORGANS)}."}
    limit = max(1, min(int(limit), 20))

    ranges = scoring.load_reference_ranges()
    values = {biomarker: float(reading[biomarker]) for biomarker in scoring.BIOMARKERS}
    fetch_limit = max(limit, config.CONFIRMED_CASE_QUERY_LIMIT)
    candidates = scoring.fetch_confirmed_cases(organ, fetch_limit)

    similarities: list[dict[str, Any]] = []
    for case in candidates:
        squared_differences = []
        for biomarker in scoring.BIOMARKERS:
            spec = ranges[organ][biomarker]
            width = max(spec.max_value - spec.min_value, 1e-9)
            normalized_difference = (values[biomarker] - float(case[biomarker])) / width
            squared_differences.append(normalized_difference**2)
        distance = math.sqrt(sum(squared_differences) / len(squared_differences))
        similarity = 1.0 / (1.0 + distance)
        similarities.append({"case_id": case["case_id"], "similarity": round(similarity, 4), "distance": round(distance, 4)})

    similarities.sort(key=lambda item: item["similarity"], reverse=True)
    closest = similarities[:limit]
    return {"organ": organ, "candidates_queried": len(candidates), "closest_confirmed_cases": closest}


def _build_investigative_tools(reading: dict[str, Any]) -> list:
    """Built per-decide()-call (closes over `reading`) rather than at module
    scope, mirroring guidance_agent.py's per-run _build_tools(state) pattern."""

    @tool
    def get_organ_reference_ranges(organ: Literal["KIDNEY", "LIVER", "ORAL"]) -> dict:
        """Look up the configured min/max/weight reference range for each biomarker
        (ph, urea_mg_dl, creatinine_umol_l, temperature_c) for one organ. Use this to
        double-check a specialist result's range_score against the actual configured
        bands rather than only trusting the pre-computed number."""
        return _tool_get_organ_reference_ranges(organ)

    @tool
    def get_closest_confirmed_cases(organ: Literal["KIDNEY", "LIVER", "ORAL"], limit: int = 5) -> dict:
        """Re-run the human-confirmed-case similarity search for one organ with a
        custom result count (default 5). specialist_results already includes each
        organ's top-3 closest confirmed cases; call this only if you genuinely want
        to look deeper than that top-3 before deciding."""
        return _tool_get_closest_confirmed_cases(reading, organ, limit)

    return [get_organ_reference_ranges, get_closest_confirmed_cases]


def decide(reading: dict[str, Any], specialist_results: list[dict[str, Any]]) -> tuple[dict[str, Any], str, dict[str, Any]]:
    """A bounded OpenRouter tool-calling loop that ends in exactly one of:
    a validated FinalDecision (returns normally), an explicit human-review
    escalation (raises HumanReviewRequested), or failure (raises
    OpenRouterDecisionError) — never a fabricated guess.

    Organ scoring (range/similarity/combined scores) is already complete by
    the time this is called; the model may optionally call
    get_organ_reference_ranges / get_closest_confirmed_cases to double-check
    that work, but never recomputes it itself.
    """
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

    investigative_tools = _build_investigative_tools(reading)

    @tool
    def flag_for_human_review(reason: str) -> str:
        """Escalate this case for a human to review instead of committing to a
        single-organ FinalDecision. This is an escape hatch for genuinely
        ambiguous or conflicting evidence, NOT the default path — most cases
        should still resolve to a direct FinalDecision. `reason` must explain
        specifically what makes the evidence inconclusive."""
        return reason

    all_tools = [*investigative_tools, flag_for_human_review, FinalDecision]
    decision_llm = llm.bind_tools(all_tools, parallel_tool_calls=False)

    ranked = sorted(compact_results, key=lambda item: item["combined_score"], reverse=True)
    deterministic_leader = ranked[0]["organ"]

    messages: list = [
        SystemMessage(content=(
            "You are the NOVERA final screening decision component. This is experimental "
            "screening support, not a confirmed diagnosis. The Kidney, Liver, and Oral "
            "specialist results were calculated before this call using project reference "
            "ranges and limited human-confirmed SQL memory. Use only the supplied evidence "
            "plus, optionally, the investigative tools below — never invent medical "
            "thresholds, diagnoses, or historical cases.\n\n"
            "Two investigative tools are available before you decide, both read-only and "
            "optional: get_organ_reference_ranges lets you double-check a specialist "
            "result's range_score against the actual configured min/max/weight bands; "
            "get_closest_confirmed_cases lets you re-run the similarity search for one "
            "organ with a larger result count than the pre-computed top-3 already on "
            "specialist_results. Call at most one or two of these, only if they would "
            "actually change your confidence, then decide.\n\n"
            "To finish, call exactly one of two tools: FinalDecision to make exactly one "
            "final prediction (KIDNEY, LIVER, or ORAL — never MULTIPLE, "
            "NO_CLEAR_PATTERN, or any other label), whose reason must mention the range "
            "score, similarity score, and confirmed-case support that drove the choice; "
            "or flag_for_human_review if, after considering the evidence, you genuinely "
            "cannot resolve the case to one organ with reasonable confidence — this is an "
            "escape hatch for real ambiguity, not a default. Most cases should resolve to "
            "a direct FinalDecision. You must end by calling one of these two tools — a "
            "plain-text reply with no tool call is never an acceptable final answer."
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

    tool_trace: list[dict[str, Any]] = []
    investigative_by_name = {t.name: t for t in investigative_tools}

    try:
        final_decision: dict[str, Any] | None = None
        final_response: AIMessage | None = None

        for _ in range(MAX_ITERATIONS):
            response = decision_llm.invoke(messages)
            messages.append(response)
            calls = _normalize_tool_calls(response)
            if not calls:
                raise OpenRouterDecisionError(
                    "OpenRouter replied without calling FinalDecision or flag_for_human_review."
                )

            stop = False
            for call in calls:
                name = call["name"]
                args = call["args"]
                call_id = call["id"]

                if name == "FinalDecision":
                    validated = FinalDecision.model_validate(args)
                    decision = validated.model_dump()
                    decision["prediction"] = str(decision["prediction"]).upper()
                    decision["confidence"] = round(float(decision["confidence"]), 4)
                    decision["reason"] = str(decision["reason"]).strip()
                    if decision["prediction"] not in scoring.ORGANS:
                        raise OpenRouterDecisionError("OpenRouter returned an unsupported prediction.")
                    if not decision["reason"]:
                        raise OpenRouterDecisionError("OpenRouter returned no explanation.")
                    tool_trace.append({"tool": name, "args": args, "result": "final decision accepted"})
                    final_decision = decision
                    final_response = response
                    stop = True
                    break

                if name == "flag_for_human_review":
                    reason = str(args.get("reason", "")).strip()
                    if not reason:
                        raise OpenRouterDecisionError("flag_for_human_review was called without a reason.")
                    tool_trace.append({"tool": name, "args": args, "result": "escalated for human review"})
                    raise HumanReviewRequested(reason)

                tool_obj = investigative_by_name.get(name)
                if tool_obj is None:
                    messages.append(ToolMessage(content=f"Unknown tool: {name}", tool_call_id=call_id))
                    tool_trace.append({"tool": name, "args": args, "result": "unknown tool, ignored"})
                    continue

                try:
                    result = tool_obj.invoke(args)
                except Exception as exc:  # noqa: BLE001 - surfaced to the model, loop continues
                    result = {"error": f"{name} raised an error: {exc}"}
                messages.append(ToolMessage(content=json.dumps(result, ensure_ascii=False), tool_call_id=call_id))
                tool_trace.append({"tool": name, "args": args, "result": _summarize_tool_result(name, result)})

            if stop:
                break
        else:
            raise OpenRouterDecisionError("The screening decision loop reached its iteration cap without a final answer.")

    except HumanReviewRequested:
        raise
    except (OpenRouterDecisionError, ValidationError) as exc:
        raise OpenRouterDecisionError("OpenRouter did not return a valid single-organ decision.") from exc
    except Exception as exc:
        raise OpenRouterDecisionError("OpenRouter could not complete the decision.") from exc

    assert final_decision is not None and final_response is not None  # guaranteed by stop/else above

    response_metadata = getattr(final_response, "response_metadata", {}) or {}
    actual_model = str(response_metadata.get("model_name") or response_metadata.get("model") or model)
    raw_result = {
        "prediction": final_decision["prediction"],
        "confidence": final_decision["confidence"],
        "reason": final_decision["reason"],
        "tool_trace": tool_trace,
    }
    return final_decision, actual_model, raw_result


def _summarize_tool_result(name: str, result: Any) -> str:
    if not isinstance(result, dict):
        return str(result)[:200]
    if "error" in result:
        return f"error: {result['error']}"
    if name == "get_organ_reference_ranges":
        return f"returned ranges for {len(result.get('ranges', {}))} biomarkers"
    if name == "get_closest_confirmed_cases":
        cases = result.get("closest_confirmed_cases", [])
        return f"returned {len(cases)} closest cases (queried {result.get('candidates_queried', 0)})"
    return "ok"


def process_case_stream(reading: dict[str, Any]):
    """Same pipeline as process_case, but a generator: yields one event after
    each real step actually completes (validate, score per organ, decide,
    persist/release), for a workflow visualizer driven by real backend
    progress rather than a decorative timer. The last event is always
    {"step": "done", "status": ..., "result": ...} carrying exactly what
    process_case() used to return directly.

    On any OpenRouter failure the case is released back to NEW with no saved
    prediction and no invented reason (req 8) — the caller sees RETRY_REQUIRED.
    On an explicit human-review escalation the case is marked RETEST_REQUIRED
    (same status/shape validation failures already use) rather than released,
    since the model made a deliberate call rather than failing outright.
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
    except HumanReviewRequested as exc:
        scoring.mark_retest_required(reading["id"], exc.reason)
        yield {"step": "decide", "status": "failed"}
        yield {
            "step": "done",
            "status": "failed",
            "result": {"status": "RETEST_REQUIRED", "case_id": reading["case_id"], "reason": exc.reason},
        }
        return
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
