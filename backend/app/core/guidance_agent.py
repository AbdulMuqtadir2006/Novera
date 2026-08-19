"""NOVERA's Guidance Agent — narrow, one-shot screening specialist (scope cut
down 2026-08-19, see novera-whatsapp-autonomous-agent-spec.md). Its job ends
at validate -> score -> decide -> report | request_retest. It used to also
own voice-script generation, self-care planning, and a hardcoded-simulated
appointment offer — all three moved to the autonomous WhatsApp Agent
(core/whatsapp_agent.py), which can now generate them contextually inside a
real conversation instead of pre-baking them on every reading regardless of
whether anyone's about to see them.

This orchestrator is real tool-calling: a `ChatOpenAI` bound to a set of
tools, in a manual invoke -> tool_calls -> ToolMessage -> invoke loop (the
same OpenRouter/ChatOpenAI pattern used throughout this codebase — see
screening_llm.decide() and appointment_graph.py — just with `.bind_tools()`
driving multi-step decisions instead of a single structured-output call).
The model decides, per run, which of {screen, report, request retest} to
invoke and in what order; the code never hardcodes that sequence.

Trigger: fired as a background asyncio task from routers/readings.py after
every POST /api/readings (the ESP32's periodic push, or a simulated one) —
never blocking that endpoint's response. Every step is broadcast live over
app/ws.py (`/ws/pipeline`) for a public homepage diagram to visualize.

Hand-off: once a screening decision is persisted, this fires a
`screening.completed` trigger into the WhatsApp Agent for every registered
user with a phone number (core/whatsapp_agent.handle_trigger) — as
independent background tasks, not awaited inline, so this run's own
throttle/lock releases promptly regardless of how long WhatsApp Agent runs
take. Whether/how to actually contact the patient is now entirely WhatsApp
Agent's call (plus the forced safety-floor guarantee in
core/whatsapp_gating.py for medium/high flags) — this file no longer decides
that itself.

Hard safety constraints enforced in this file:
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

from .. import config, db, ws
from . import content_llm, reasoning_stream, reference_data, scoring, screening_llm, whatsapp_agent

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 6
THROTTLE_SECONDS = 60

SYSTEM_PROMPT = (
    "You are Novera's Guidance Agent. A new saliva reading has just arrived. "
    "Always start by calling run_screening_pipeline — never guess an organ or a "
    "flag yourself. Based on its result: a report is worth generating for "
    "medium/high flags, and often for low flags too. If validation failed or "
    "the pipeline could not produce a confident result, call request_retest "
    "instead of guessing — do not call it after a successful, confident "
    "screening. You do not decide whether to contact the patient or how — "
    "that is the WhatsApp Agent's job now, triggered automatically once you "
    "finish. Use your judgment: you do not need to call every tool every run. "
    "Stop once you've made a reasonable set of decisions and reply with a "
    "short final summary."
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
    # Multi-tenant (2026-08-19): the single user this reading belongs to —
    # every tool in this run operates on their data only, and the
    # screening.completed hand-off at the end targets them alone (see run()).
    user_id: int
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


def _load_reading(user_id: int) -> Optional[dict[str, Any]]:
    row = reference_data.get_latest_row(user_id)
    return reference_data.row_to_reading(row) if row else None


def _get_user_by_id(user_id: int) -> Optional[dict[str, Any]]:
    return db.fetch_one("SELECT id, email, name, phone FROM users WHERE id = %s", (user_id,))


async def _dispatch_screening_completed(run_id: str, user: dict[str, Any], payload: dict[str, Any]) -> None:
    """Isolated per-user task — one user's WhatsApp Agent run failing (or
    hanging) never affects another's or this guidance run's own lifecycle,
    since guidance_agent.run() has already moved on to its own run_end by
    the time these are actually executing."""
    try:
        await asyncio.to_thread(whatsapp_agent.handle_trigger, "screening.completed", user, payload)
    except Exception:
        logger.exception("guidance_agent run %s: screening.completed dispatch failed for user_id=%s",
                          run_id, user.get("id"))


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
            case_row = await asyncio.to_thread(scoring.claim_new_case_from_latest_reading, state.user_id)
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
            reading = state.reading or await asyncio.to_thread(_load_reading, state.user_id)
            state.reading = reading
            if reading is None:
                await _emit(state.run_id, "tool_report", "error", "No reading available")
                return "No reading available to generate a report from."
            ctx = state.ctx if state.ctx is not None else await asyncio.to_thread(reference_data.get_context, state.user_id)
            state.ctx = ctx
            await asyncio.to_thread(content_llm.report_agent, reading, ctx, state.user_id, "en")
        except Exception as exc:
            logger.exception("generate_report failed")
            await _emit(state.run_id, "tool_report", "error", "Report generation failed")
            return f"Report generation failed: {exc}"
        state.actions.append("report generated")
        state.action_tokens.append("report")
        await _emit(state.run_id, "tool_report", "success", "Report generated")
        return "Report generated successfully."

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


async def run(reading_row: dict[str, Any]) -> None:
    """Entry point: fired as a background asyncio task from
    routers/readings.py right after a reading is inserted and claimed.
    Never raises — every failure path ends in a `run_end` error event.

    Multi-tenant (2026-08-19): `reading_row["user_id"]` (set by
    routers/readings.py from device_state.pending_sample_user_id at insert
    time) is now actually used — an orphaned/unrequested reading (nobody
    armed the shared device for anyone) has no one to screen for, so this
    returns immediately without touching the throttle lock at all, leaving
    that slot free for a real per-user run. run_screening_pipeline still
    re-fetches via scoring.claim_new_case_from_latest_reading(user_id), the
    same shared helper routers/screening.py uses, just now scoped.
    """
    user_id = reading_row.get("user_id")
    if user_id is None:
        logger.info("guidance_agent: orphaned/unrequested reading (no owner), skipping autonomous run")
        return
    if not config.AUTO_AGENT_ENABLED:
        return
    if not _try_acquire():
        return

    run_id = str(uuid.uuid4())
    state = _RunState(run_id=run_id, user_id=user_id)

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
                # Real, permanent status update — fills the gap between the
                # last tool completing and the narration lines arriving with
                # something true, rather than a silent stall.
                await ws.broadcast(
                    {
                        "type": "narration",
                        "runId": run_id,
                        "source": "device",
                        "label": "Preparing reasoning stream...",
                        "ts": _now_iso(),
                    }
                )
                # Hard timeout around this whole call, independent of
                # whatever timeout/retry settings ChatOpenAI itself is
                # configured with. This feature is decorative enrichment —
                # it must NEVER be able to block the throttle/_in_progress
                # lock indefinitely, since that would jam every future
                # autonomous run until the server restarts. asyncio.wait_for
                # can't force-kill the underlying network thread if it's
                # truly stuck, but it guarantees `run()` itself moves on and
                # reaches the finally block below that releases the lock.
                try:
                    narration_lines = await asyncio.wait_for(
                        asyncio.to_thread(
                            reasoning_stream.generate_reasoning_stream,
                            state.organ,
                            state.confidence,
                            state.reason or "",
                            state.flag,
                            state.matched_cases,
                            state.action_tokens,
                        ),
                        timeout=25.0,
                    )
                except asyncio.TimeoutError:
                    logger.warning("guidance_agent run %s: reasoning stream narration timed out, skipping", run_id)
                    narration_lines = None
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

            if state.organ:
                # Hand-off point (spec §2): screening finished, fire
                # screening.completed for the single user this reading
                # belongs to — CORRECTED 2026-08-19 (same day as the
                # multi-tenant migration): this used to fan out to every
                # registered user with a phone number, under the
                # now-superseded assumption that screening data was
                # global/shared. Not awaited here, so this run's own
                # throttle lock (see finally: _release() below) isn't held
                # hostage by however long WhatsApp Agent's model loop takes.
                try:
                    owner = await asyncio.to_thread(_get_user_by_id, state.user_id)
                except Exception:
                    logger.exception("guidance_agent run %s: failed to load owning user for screening.completed handoff", run_id)
                    owner = None
                if owner and owner.get("phone"):
                    payload = {"case_id": state.case_row["case_id"] if state.case_row else None,
                               "organ": state.organ, "flag": state.flag}
                    asyncio.create_task(_dispatch_screening_completed(run_id, owner, payload))

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
