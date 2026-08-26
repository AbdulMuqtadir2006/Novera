"""Shared helper for sanitizing raw LLM output before it's ever shown to a
patient, parsed as JSON, or used as narration text.

Found live 2026-08-26: a patient received a raw reasoning trace concatenated
directly onto the WhatsApp agent's actual reply with no separator at all
("...Just respondHi NOVERA..."), because some models (routed through
OpenRouter) emit their chain-of-thought inline inside the response content
itself, wrapped in <think>/<thinking> tags, rather than in a separate
structured field LangChain exposes apart from .content — and nothing in
this codebase stripped it before treating .content as the final answer.
"""
from __future__ import annotations

import re

# DOTALL so a multi-line reasoning block is removed as one unit;
# case-insensitive since tag casing isn't guaranteed across models/providers.
_THINK_BLOCK_RE = re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>", re.DOTALL | re.IGNORECASE)
# Defensive fallback for an unterminated block (a response cut off by a
# token/length limit mid-thought, or a model that never emits the closing
# tag) — strip the opening tag and everything after it rather than ship a
# half-finished reasoning trace as if it were the real answer.
_UNCLOSED_THINK_RE = re.compile(r"<think(?:ing)?>.*", re.DOTALL | re.IGNORECASE)


def strip_reasoning(text: str) -> str:
    """Remove any <think>/<thinking> block from raw model output. Safe to
    call on text with no such block at all — returns it unchanged apart from
    surrounding whitespace."""
    if not text:
        return text
    cleaned = _THINK_BLOCK_RE.sub("", text)
    cleaned = _UNCLOSED_THINK_RE.sub("", cleaned)
    return cleaned.strip()
