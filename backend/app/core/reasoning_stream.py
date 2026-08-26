"""Reasoning-stream narration for WhatsApp Agent's live workflow ticker.

One additional, single-shot LLM call made *after* whatsapp_agent.py's real
tool-calling loop has already run run_screening_pipeline and already decided
(for real) which actions to take (moved here from guidance_agent.py in the
2026-08-20 orchestrator merge — guidance_agent.py no longer exists). This
module never decides anything — it narrates an already-completed outcome.
The forced-override in generate_reasoning_stream() (replacing the model's own
final `> Decision: ...` line with one built directly from the real
action_tokens list) is what keeps that true: nothing broadcast to the public
/ws/pipeline socket is ever the LLM's own claim about what happened, only
code's.

Decorative enrichment, not required for a run to succeed — any failure here
(LLM not configured, network error, malformed response) returns None and the
caller skips narration entirely, exactly as if this module didn't exist.
"""
from __future__ import annotations

import logging

from . import content_llm, llm_text

logger = logging.getLogger(__name__)

MAX_LINES = 9
MAX_LINE_LENGTH = 140

SYSTEM_PROMPT = """You are the reasoning stream generator for the Novera Guidance Agent. You receive, in one call, the completed screening decision (organ, confidence, reason) and whatever context/confirmed-case/clinic data has already been fetched for this patient. Your job is to produce a short, live-feeling reasoning stream — as if you are working step by step through memory and available actions — followed by a final decision. You are not looping or calling anything yourself; you are narrating a single pass over the data you were given.

## Output format

Emit 5 to 8 lines, each prefixed with `> `, terminal-log style: short, declarative, present tense, no more than ~12 words per line. Each line should read like a distinct beat of reasoning — checking a source, noting a finding, weighing an option — not a summary paragraph. End with exactly one final line:

```
> Decision: [comma-separated list of chosen actions]
```

Actions are always chosen from: `report`, `voice_script`, `self_care_plan`, `clinic_offer`, `request_retest`.

## Rules

1. Every specific number, count, or outcome you state (case counts, slot counts, trend direction, confidence level) must come directly from the data provided in this call. Never invent a figure that wasn't given to you.
2. If a line implies checking something you don't have data for, phrase it generically ("Checking confirmed cases...") without stating a specific result — never fill in a plausible-sounding number to complete the sentence.
3. Keep every line grounded in something real: the actual organ, the actual confidence level, the actual reason string, the actual confirmed-case or clinic data passed in. Don't reference a tool or memory source that wasn't part of your input.
4. Apply the same selection logic every time, regardless of how the narration is worded:
   - `clinic_offer` only if the input data indicates an available slot.
   - `self_care_plan` only if confidence is medium or high.
   - `request_retest` only if confidence is low, replacing `report` and `voice_script` rather than joining them.
   - `report` and `voice_script` are the default pairing for any confident result.
5. No hedging language, no apologies, no explanations of your own process — just the log lines and the final decision."""


def _build_user_message(
    organ: str,
    confidence: float,
    reason: str,
    flag: str,
    matched_cases: int | None,
    action_tokens: list[str],
) -> str:
    # Deliberately NOT including the raw `reason` string here, even though the
    # spec's rule 3 lists "the actual reason string" as groundable material —
    # screening_llm.decide()'s reason text is written by a *different* LLM
    # call with no instruction against citing raw biomarker values, and in
    # practice it sometimes does (observed live: "...pH 7.33 falling
    # within..."). Feeding that into this prompt risks a second LLM echoing a
    # raw reading into a narration line that DOES get broadcast to the public,
    # unauthenticated /ws/pipeline socket — exactly the category of leak this
    # broadcast system is built to prevent everywhere else. `reason` is kept
    # as a parameter (unused below) so the call site doesn't need to change if
    # a safely-redacted version becomes available later.
    del reason
    confidence_pct = f"{confidence * 100:.0f}%"
    if matched_cases is None:
        matched_cases_line = "Confirmed-case match count: not available for this run."
    else:
        matched_cases_line = f"Confirmed-case match count: {matched_cases} (out of up to 3 considered)."

    if action_tokens:
        actions_line = f"Actions actually taken this run: {', '.join(action_tokens)}."
    else:
        actions_line = "No actions were taken this run."

    return (
        f"Organ flagged: {organ}\n"
        f"Confidence: {confidence_pct} ({flag})\n"
        f"{matched_cases_line}\n"
        f"{actions_line}\n\n"
        "Narrate this single completed pass per the system instructions, ending with the "
        "Decision line. Ground every line only in the facts given above — you do not have "
        "the underlying screening reason text, so don't reference specific biomarker values "
        "or thresholds; speak generically about checking evidence/memory/confidence instead."
    )


def _parse_lines(raw: str) -> list[str]:
    """Lenient parser: the spec asks the model for `> `-prefixed lines, but
    cheap/fast content models don't always follow formatting instructions to
    the letter (may drop the prefix, wrap the whole thing in a markdown code
    fence, or use `-`/`*` bullets instead). Being strict here means a purely
    cosmetic formatting miss silently kills the whole feature (returns None),
    which defeats the point — so this accepts any non-empty, non-heading line
    regardless of exactly how it's decorated, and strips decoration uniformly.
    Returned lines are PLAIN TEXT (no `> ` prefix) — the frontend ticker
    already renders its own `> ` glyph for every entry, mechanical or
    narrated, so a prefix baked in here would double up as `> > text`."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        head, _, rest = text.partition("\n")
        if rest and len(head) < 20:  # drop a leading ```json / ```text tag line
            text = rest

    lines: list[str] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith("> "):
            stripped = stripped[2:].strip()
        elif stripped[:1] == ">":
            stripped = stripped[1:].strip()
        elif stripped[:2] in ("- ", "* "):
            stripped = stripped[2:].strip()
        elif stripped.startswith("#") or stripped.startswith("```"):
            continue  # stray markdown heading/fence remnant, not a log line
        if not stripped:
            continue
        if len(stripped) > MAX_LINE_LENGTH:
            stripped = stripped[:MAX_LINE_LENGTH].rstrip()
        lines.append(stripped)
        if len(lines) >= MAX_LINES:
            break
    return lines


def generate_reasoning_stream(
    organ: str,
    confidence: float,
    reason: str,
    flag: str,
    matched_cases: int | None,
    action_tokens: list[str],
) -> list[str] | None:
    """Returns a short list of plain-text narration lines ending with a
    forced, code-constructed "Decision: ..." line, or None on any failure
    (never raises). The Decision line is ALWAYS overwritten with the real
    action_tokens list regardless of what the LLM produced — see module
    docstring."""
    try:
        llm = content_llm.make_llm(temperature=0.5, max_tokens=400)
        user_message = _build_user_message(organ, confidence, reason, flag, matched_cases, action_tokens)
        response = llm.invoke(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ]
        )
        lines = _parse_lines(llm_text.strip_reasoning(str(response.content)))
        if len(lines) < 2:
            logger.info("generate_reasoning_stream: fewer than 2 usable lines parsed, skipping narration")
            return None

        forced_decision = f"Decision: {', '.join(action_tokens) if action_tokens else 'none'}"
        if lines[-1].lower().startswith("decision:"):
            lines[-1] = forced_decision
        else:
            lines.append(forced_decision)
            if len(lines) > MAX_LINES:
                lines = lines[: MAX_LINES - 1] + [forced_decision]

        return lines
    except Exception:
        logger.exception("generate_reasoning_stream failed")
        return None
