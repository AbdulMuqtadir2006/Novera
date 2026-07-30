"""OpenRouter LLM access + robust JSON-structured calls.

Free OpenRouter models vary in how well they support forced tool-calling, so
for content agents we ask for strict JSON in the text and parse it defensively,
validating against a Pydantic model. Anything that fails raises LLMError and the
caller falls back to deterministic output.
"""
from __future__ import annotations

import json
import re
from typing import Type, TypeVar

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ValidationError

from . import config

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


def make_llm(temperature: float = 0.3, max_tokens: int = 1200) -> ChatOpenAI:
    if not config.AI_ENABLED:
        raise LLMError("OPENROUTER_API_KEY not configured (must start with sk-or-).")
    return ChatOpenAI(
        model=config.RESOLVED_MODEL,
        api_key=config.OPENROUTER_API_KEY,
        base_url=config.OPENROUTER_BASE_URL,
        temperature=temperature,
        timeout=config.OPENROUTER_TIMEOUT,
        max_retries=1,
        max_tokens=max_tokens,
        default_headers={
            "HTTP-Referer": "http://localhost",
            "X-Title": "NOVERA Agentic Core",
        },
    )


def _extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model response (handles code fences)."""
    if not text:
        raise LLMError("Empty model response.")
    # Strip ```json ... ``` fences if present.
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        # Fall back to the outermost braces.
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise LLMError("No JSON object found in model response.")
        candidate = text[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise LLMError(f"Model returned invalid JSON: {exc}") from exc


def structured_json_call(
    system: str,
    user: str,
    model_cls: Type[T],
    temperature: float = 0.3,
    max_tokens: int = 1400,
) -> T:
    """Call the LLM and validate its JSON output against `model_cls`."""
    schema = json.dumps(model_cls.model_json_schema(), ensure_ascii=False)
    full_system = (
        f"{system}\n\n"
        "Respond with ONE valid JSON object only — no prose, no markdown, no code "
        "fences. It must match this JSON schema (keys and types):\n"
        f"{schema}"
    )
    llm = make_llm(temperature=temperature, max_tokens=max_tokens)
    try:
        response = llm.invoke(
            [
                {"role": "system", "content": full_system},
                {"role": "user", "content": user},
            ]
        )
    except Exception as exc:  # network / provider / auth
        raise LLMError(f"LLM call failed: {exc}") from exc

    data = _extract_json(str(response.content))
    try:
        return model_cls.model_validate(data)
    except ValidationError as exc:
        raise LLMError(f"Model output failed validation: {exc}") from exc


def text_call(system: str, user: str, temperature: float = 0.4, max_tokens: int = 800) -> str:
    llm = make_llm(temperature=temperature, max_tokens=max_tokens)
    try:
        response = llm.invoke(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
        )
    except Exception as exc:
        raise LLMError(f"LLM call failed: {exc}") from exc
    return str(response.content).strip()
