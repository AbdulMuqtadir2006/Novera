"""NOVERA's autonomous Guidance Agent — the one genuinely agentic capability
in this backend (everything else is "LLM-in-the-loop structured decisioning":
one prompt in, one JSON object out, code decides what happens next).

This orchestrator is real tool-calling: a `ChatOpenAI` bound to a set of
tools, in a manual invoke -> tool_calls -> ToolMessage -> invoke loop (the
same OpenRouter/ChatOpenAI pattern used throughout this codebase — see
screening_llm.decide() and appointment_graph.py — just with `.bind_tools()`
driving multi-step decisions instead of a single structured-output call).
The model decides, per run, which of {screen, report, voice, self-care,
offer appointment, request retest} to invoke and in what order; the code
never hardcodes that sequence.

Trigger: fired as a background asyncio task from routers/readings.py after
every POST /api/readings (the ESP32's periodic push, or a simulated one) —
never blocking that endpoint's response. Every step is broadcast live over
app/ws.py (`/ws/pipeline`) for a public homepage diagram to visualize.

Hard safety constraints enforced in this file:
  - offer_clinic_appointment() ALWAYS calls appointment_graph.send_offer
    with simulate=True hardcoded — never a real WhatsApp send, no config
    flag can change that.
  - config.AUTO_AGENT_ENABLED is the kill switch (checked by the caller in
    routers/readings.py) and is checked again here for defense in depth.
  - A 60s in-memory throttle (single Railway instance, no distributed
    coordination needed) prevents overlapping/back-to-back runs; throttled
    runs emit nothing and fail silently.
  - Every exception is caught here — a failed run ends with a `run_end`
    error event, never a silently swallowed background-task crash.
  - Broadcast payloads (see _emit/_run_start/_run_end below) carry only
    node/status/organ-category/coarse-flag/model-name/short labels — never
    raw biomarker values, patient identifiers, or free-text diagnosis/notes.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from .. import config, ws
from . import appointment_graph, content_llm, reasoning_stream, reference_data, scoring, screening_llm

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 6
THROTTLE_SECONDS = 60

SYSTEM_PROMPT = (
    "You are Novera's Guidance Agent. A new saliva reading has just arrived. "
    "Always start by calling run_screening_pipeline — never guess an organ or a "
    "flag yourself. Based on its result: if the flag is medium or high, generate "
    "a report and a voice script, and consider offering a clinic appointment "
    "(this is always simulated, never a real send). If the flag is low, a report "
    "is still useful but a clinic offer is usually unnecessary. A self-care plan "
    "is worth generating when there's a specific area of concern to guide. If "
    "validation failed or the pipeline could not produce a confident result, "
    "call request_retest instead of guessing — do not call it after a "
    "successful, confident screening. Use your judgment: you do not need to "
    "call every tool every run. Stop once you've made a reasonable set of "
    "decisions and reply with a short final summary."
)


# ---------------------------------------------------------------------------
# throttle / in-flight guard — single in-memory instance is fine (req: no
# distributed coordination needed for this Railway single-instance deploy).
# ---------------------------------------------------------------------------
_in_progress = False
_last_completed_at: Optional[float] = None


def _try_acquire() -> bool:
    global _in_progress, _last_completed_at
    if _in_progress:
        return False
    now = time.monotonic()
    if _last_completed_at is not None and (now - _last_completed_at) < THROTTLE_SECONDS:
        return False
    _in_progress = True
    return True


def _release() -> None:
    global _in_progress, _last_completed_at
    _in_progress = False
    _last_completed_at = time.monotonic()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _emit(run_id: str, node: str, status: str, label: str) -> None:
    await ws.broadcast(
        {
            "type": "step",
            "runId": run_id,
            "source": "device",
            "node": node,
            "status": status,
            "label": label,
            "ts": _now_iso(),
        }
    )


# ---------------------------------------------------------------------------
# per-run state, shared by closures below via _build_tools()
# ---------------------------------------------------------------------------
@dataclass
class _RunState:
    run_id: str
    case_row: Optional[dict[str, Any]] = None
    reading: Optional[dict[str, Any]] = None
    ctx: Optional[dict[str, Any]] = None
    screening_done: bool = False
    validation_failed: bool = False
    retest_requested: bool = False
    organ: Optional[str] = None
    confidence: Optional[float] = None
    flag: Optional[str] = None
    reason: Optional[str] = None
    actions: list[str] = field(default_factory=list)
    hit_iteration_cap: bool = False
    matched_cases: Optional[int] = None
    # Canonical action vocabulary appended alongside the human-readable
    # `actions` strings above — the single source of truth the forced
    # reasoning-stream Decision line is built from (never parsed out of the
    # human-readable strings). See reasoning_stream.generate_reasoning_stream.
    action_tokens: list[str] = field(default_factory=list)


def _load_reading() -> Optional[dict[str, Any]]:
    row = reference_data.get_latest_row()
    return reference_data.row_to_reading(row) if row else None


def _build_tools(state: _RunState) -> list:
    @tool
    async def run_screening_pipeline() -> str:
        """Claim the latest saliva reading into a new screening case and run the
        deterministic organ-screening pipeline (validate -> score KIDNEY/STOMACH/
        ORAL -> single screening decision call). Always call this first — it is
        the only source of the organ prediction, confidence, and flag."""
        if state.screening_done:
            return "The screening pipeline has already run this session; do not call it again."

        try:
            case_row = await asyncio.to_thread(scoring.claim_new_case_from_latest_reading)
        except Exception as exc:
            logger.exception("claim_new_case_from_latest_reading failed")
            return f"Could not claim a new screening case: {exc}"
        if case_row is None:
            return "No reading is available to screen."
        state.case_row = case_row

        await _emit(state.run_id, "validate", "start", "Validating reading")
        try:
            errors = await asyncio.to_thread(scoring.validate_reading, case_row)
        except Exception as exc:
            await _emit(state.run_id, "validate", "error", "Validation failed")
            logger.exception("validate_reading failed")
            return f"Validation step raised an error: {exc}"

        if errors:
            reason = "; ".join(errors)
            await _emit(state.run_id, "validate", "error", "Validation failed")
            await asyncio.to_thread(scoring.mark_retest_required, case_row["id"], reason)
            state.screening_done = True
            state.validation_failed = True
            return (
                f"Validation failed ({reason}). The case has been marked RETEST_REQUIRED "
                "already — do not call request_retest for this."
            )
        await _emit(state.run_id, "validate", "success", "Reading validated")

        values = {b: float(case_row[b]) for b in scoring.BIOMARKERS}
        engine = await asyncio.to_thread(scoring.get_engine)
        node_map = {"KIDNEY": "score_kidney", "STOMACH": "score_stomach", "ORAL": "score_oral"}
        specialist_results = []
        for organ in scoring.ORGANS:
            node = node_map[organ]
            await _emit(state.run_id, node, "start", f"Scoring {organ.title()}")
            result = await asyncio.to_thread(engine.evaluate, organ, values)
            specialist_results.append(result)
            await _emit(state.run_id, node, "success", f"{organ.title()} fit: {result['flag']}")

        await _emit(state.run_id, "agent", "start", "Making screening decision")
        try:
            decision, model, raw_result = await asyncio.to_thread(
                screening_llm.decide, case_row, specialist_results
            )
        except screening_llm.HumanReviewRequested as exc:
            await _emit(state.run_id, "tool_retest", "start", "Flagging for human review")
            try:
                await asyncio.to_thread(scoring.mark_retest_required, case_row["id"], exc.reason)
            except Exception as mark_exc:
                logger.exception("mark_retest_required failed after HumanReviewRequested")
                await _emit(state.run_id, "tool_retest", "error", "Failed to flag for human review")
                state.screening_done = True
                return f"The screening decision was flagged for human review, but saving that status failed: {mark_exc}"
            await _emit(state.run_id, "tool_retest", "success", "Flagged for human review")
            state.screening_done = True
            state.retest_requested = True
            state.actions.append("flagged for human review")
            return (
                f"The screening decision component flagged this case for human review "
                f"(reason: {exc.reason}). The case has already been marked RETEST_REQUIRED — "
                "do not call request_retest for this case."
            )
        except screening_llm.OpenRouterDecisionError:
            await asyncio.to_thread(scoring.release_reading, case_row["id"])
            await _emit(state.run_id, "agent", "error", "Screening decision failed")
            state.screening_done = True
            return (
                "The screening decision call failed; the case was released back to NEW "
                "(no prediction saved). Consider calling request_retest."
            )

        await asyncio.to_thread(
            scoring.persist_decision, case_row, decision, specialist_results, model, raw_result
        )
        flag = next(
            (r["flag"] for r in specialist_results if r["organ"] == decision["prediction"]),
            "medium",
        )
        state.matched_cases = next(
            (r["matched_cases"] for r in specialist_results if r["organ"] == decision["prediction"]),
            None,
        )
        await _emit(
            state.run_id,
            "agent",
            "success",
            f"Screening flagged {decision['prediction']} ({flag} confidence)",
        )

        state.screening_done = True
        state.organ = decision["prediction"]
        state.confidence = decision["confidence"]
        state.flag = flag
        state.reason = decision.get("reason")
        return (
            f"Screening complete. Predicted organ: {decision['prediction']}, "
            f"confidence: {decision['confidence']:.2f}, flag: {flag}. Use this to decide "
            "whether to generate a report/voice script/self-care plan, offer a clinic "
            "appointment, or (only if this had failed) request a retest."
        )

    @tool
    async def generate_report() -> str:
        """Generate the plain-language screening report (per-area notes +
        recommendation) for the current reading, taking any doctor-provided
        context into account. Useful for medium/high flags, and often for low
        flags too."""
        await _emit(state.run_id, "tool_report", "start", "Generating report")
        try:
            reading = state.reading or await asyncio.to_thread(_load_reading)
            state.reading = reading
            if reading is None:
                await _emit(state.run_id, "tool_report", "error", "No reading available")
                return "No reading available to generate a report from."
            ctx = state.ctx if state.ctx is not None else await asyncio.to_thread(reference_data.get_context)
            state.ctx = ctx
            await asyncio.to_thread(content_llm.report_agent, reading, ctx, "en")
        except Exception as exc:
            logger.exception("generate_report failed")
            await _emit(state.run_id, "tool_report", "error", "Report generation failed")
            return f"Report generation failed: {exc}"
        state.actions.append("report generated")
        state.action_tokens.append("report")
        await _emit(state.run_id, "tool_report", "success", "Report generated")
        return "Report generated successfully."

    @tool
    async def generate_voice_script() -> str:
        """Generate the spoken (text-to-speech) screening summary script for the
        current reading."""
        await _emit(state.run_id, "tool_voice", "start", "Generating voice script")
        try:
            reading = state.reading or await asyncio.to_thread(_load_reading)
            state.reading = reading
            if reading is None:
                await _emit(state.run_id, "tool_voice", "error", "No reading available")
                return "No reading available to generate a voice script from."
            await asyncio.to_thread(content_llm.voice_agent, reading, "en")
        except Exception as exc:
            logger.exception("generate_voice_script failed")
            await _emit(state.run_id, "tool_voice", "error", "Voice script generation failed")
            return f"Voice script generation failed: {exc}"
        state.actions.append("voice script generated")
        state.action_tokens.append("voice_script")
        await _emit(state.run_id, "tool_voice", "success", "Voice script generated")
        return "Voice script generated successfully."

    @tool
    async def generate_self_care_plan() -> str:
        """Generate a personalised diet/self-care plan from the current reading,
        doctor context, and chat history. Best used when there's a specific area
        of concern worth guiding the patient on."""
        await _emit(state.run_id, "tool_selfcare", "start", "Generating self-care plan")
        try:
            reading = state.reading or await asyncio.to_thread(_load_reading)
            state.reading = reading
            if reading is None:
                await _emit(state.run_id, "tool_selfcare", "error", "No reading available")
                return "No reading available to generate a self-care plan from."
            ctx = state.ctx if state.ctx is not None else await asyncio.to_thread(reference_data.get_context)
            state.ctx = ctx
            history = await asyncio.to_thread(reference_data.get_chat_history)
            await asyncio.to_thread(content_llm.self_care_agent, reading, ctx, history, "en")
        except Exception as exc:
            logger.exception("generate_self_care_plan failed")
            await _emit(state.run_id, "tool_selfcare", "error", "Self-care plan generation failed")
            return f"Self-care plan generation failed: {exc}"
        state.actions.append("self-care plan generated")
        state.action_tokens.append("self_care_plan")
        await _emit(state.run_id, "tool_selfcare", "success", "Self-care plan generated")
        return "Self-care plan generated successfully."

    @tool
    async def offer_clinic_appointment() -> str:
        """Offer the patient a clinic appointment. SAFETY: this always runs in
        simulation mode — it never sends a real WhatsApp message or books a real
        appointment, regardless of what you intend. Use it when the flag is
        medium/high and a follow-up visit seems warranted."""
        await _emit(state.run_id, "tool_whatsapp", "start", "Preparing appointment offer (simulated)")
        try:
            to = config.WHATSAPP_TO or "0000000000"
            case_id = state.case_row["case_id"] if state.case_row else None
            # simulate=True is hardcoded and unconditional — this call path must
            # never send a real WhatsApp message (hard safety constraint).
            await asyncio.to_thread(appointment_graph.send_offer, to, case_id, True)
        except Exception as exc:
            logger.exception("offer_clinic_appointment failed")
            await _emit(state.run_id, "tool_whatsapp", "error", "Appointment offer simulation failed")
            return f"Appointment offer simulation failed: {exc}"
        state.actions.append("appointment offer simulated")
        state.action_tokens.append("clinic_offer")
        await _emit(state.run_id, "tool_whatsapp", "success", "Appointment offer simulated")
        return "Appointment offer simulated successfully (no real message was sent)."

    @tool
    async def request_retest(reason: str) -> str:
        """Flag the current case as needing a retest instead of guessing — use
        this only when validation failed or the screening pipeline could not
        produce a confident result. `reason` is a short explanation."""
        await _emit(state.run_id, "tool_retest", "start", "Flagging for retest")
        try:
            if state.case_row:
                await asyncio.to_thread(scoring.mark_retest_required, state.case_row["id"], reason)
        except Exception as exc:
            logger.exception("request_retest failed")
            await _emit(state.run_id, "tool_retest", "error", "Retest request failed")
            return f"Retest request failed: {exc}"
        state.retest_requested = True
        state.actions.append("retest requested")
        state.action_tokens.append("request_retest")
        await _emit(state.run_id, "tool_retest", "success", "Retest requested")
        return "Retest requested successfully."

    return [
        run_screening_pipeline,
        generate_report,
        generate_voice_script,
        generate_self_care_plan,
        offer_clinic_appointment,
        request_retest,
    ]


def _summarize(state: _RunState) -> str:
    """Builds the public run_end label from bounded, categorical state only —
    deliberately never from the model's own free-form text, since that text
    is drawn from a message history that includes precise confidence scores
    and would risk leaking more than the coarse flag this endpoint is allowed
    to broadcast (hard safety constraint: no PII / raw values on the WS)."""
    suffix = " (stopped at the action cap)" if state.hit_iteration_cap else ""
    if state.organ:
        parts = [f"{state.organ} flagged ({state.flag})"]
        if state.actions:
            parts.append(", ".join(state.actions))
        return "Completed — " + "; ".join(parts) + suffix
    if state.validation_failed or state.retest_requested:
        return "Completed — reading did not produce a confident screening result, retest requested" + suffix
    return "Completed — no action taken" + suffix


async def run(reading_row: dict[str, Any]) -> None:  # noqa: ARG001 - see below
    """Entry point: fired as a background asyncio task from
    routers/readings.py right after a reading is inserted and claimed.
    Never raises — every failure path ends in a `run_end` error event.

    `reading_row` (the just-inserted reading, already shaped by
    reference_data.row_to_reading()) is accepted per the entry-point contract
    but not read directly: the run_screening_pipeline tool re-fetches the
    latest reading itself via scoring.claim_new_case_from_latest_reading(),
    the same shared helper routers/screening.py uses, so there's exactly one
    code path for "turn the latest reading into a claimed screening case"
    rather than two that could drift apart.
    """
    if not config.AUTO_AGENT_ENABLED:
        return
    if not _try_acquire():
        return

    run_id = str(uuid.uuid4())
    state = _RunState(run_id=run_id)

    try:
        await ws.broadcast(
            {
                "type": "run_start",
                "runId": run_id,
                "source": "device",
                "node": "device",
                "status": "success",
                "label": "New reading received",
                "ts": _now_iso(),
            }
        )

        if not config.AI_ENABLED:
            logger.info("guidance_agent run %s: AI not configured, no autonomous action taken", run_id)
        else:
            tools = _build_tools(state)
            tool_map = {t.name: t for t in tools}
            llm = ChatOpenAI(
                model=config.OPENROUTER_MODEL_SCREENING,
                api_key=config.OPENROUTER_API_KEY,
                base_url=config.OPENROUTER_BASE_URL,
                temperature=0,
                timeout=config.OPENROUTER_TIMEOUT_SECONDS,
                max_retries=0,
                default_headers={"HTTP-Referer": "http://localhost", "X-Title": "NOVERA Guidance Agent"},
            ).bind_tools(tools)

            messages: list = [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content="A new saliva reading just arrived. Decide what to do."),
            ]

            for _ in range(MAX_ITERATIONS):
                response = await asyncio.to_thread(llm.invoke, messages)
                messages.append(response)
                tool_calls = getattr(response, "tool_calls", None) or []
                if not tool_calls:
                    # The model's free-form closing text may reference precise
                    # confidence scores from the tool-call history — log it
                    # server-side only, never broadcast it (see _summarize's
                    # docstring for why the public label stays categorical).
                    if isinstance(response.content, str) and response.content.strip():
                        logger.info("guidance_agent run %s final note: %s", run_id, response.content.strip())
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
                            result_text = await tool_obj.ainvoke(args)
                        except Exception as exc:
                            logger.exception("guidance_agent tool %r raised", name)
                            result_text = f"Tool {name} raised an unexpected error: {exc}"
                    messages.append(ToolMessage(content=str(result_text), tool_call_id=call_id))
            else:
                state.hit_iteration_cap = True

            if state.organ:
                # TEMP DIAGNOSTIC (2026-08-15): confirms this branch is
                # actually reached before the LLM call — remove once the
                # narration feature is confirmed working live, see chat.
                await ws.broadcast(
                    {
                        "type": "narration",
                        "runId": run_id,
                        "source": "device",
                        "label": "Preparing reasoning stream...",
                        "ts": _now_iso(),
                    }
                )
                narration_lines = await asyncio.to_thread(
                    reasoning_stream.generate_reasoning_stream,
                    state.organ,
                    state.confidence,
                    state.reason or "",
                    state.flag,
                    state.matched_cases,
                    state.action_tokens,
                )
                if narration_lines:
                    for line in narration_lines:
                        # Strip the "> " prefix reasoning_stream.py keeps (it
                        # matches the spec's literal output format) — the
                        # frontend ticker already renders its own "> " glyph
                        # for every entry uniformly, so broadcasting it too
                        # would double up as "> > text".
                        clean_line = line[2:] if line.startswith("> ") else line
                        await ws.broadcast(
                            {
                                "type": "narration",
                                "runId": run_id,
                                "source": "device",
                                "label": clean_line,
                                "ts": _now_iso(),
                            }
                        )
                        await asyncio.sleep(0.4)

        await ws.broadcast(
            {
                "type": "run_end",
                "runId": run_id,
                "source": "device",
                "node": "agent",
                "status": "success",
                "label": _summarize(state),
                "ts": _now_iso(),
            }
        )
    except Exception:
        logger.exception("guidance_agent run %s failed", run_id)
        try:
            await ws.broadcast(
                {
                    "type": "run_end",
                    "runId": run_id,
                    "source": "device",
                    "node": "agent",
                    "status": "error",
                    "label": "Run failed with an internal error",
                    "ts": _now_iso(),
                }
            )
        except Exception:
            logger.exception("guidance_agent run %s: failed to broadcast run_end error", run_id)
    finally:
        _release()
