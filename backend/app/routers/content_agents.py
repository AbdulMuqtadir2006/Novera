from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import db
from ..core import content_llm, emergency, reference_data
from ..deps import require_user
from ..rate_limit import limiter
from ..schemas import ChatSendReq, LangReq, SelfCareReq

router = APIRouter()


# Bug fix (2026-08-22): none of these OpenRouter-calling endpoints had any
# rate limit (only auth.py's signup/login did) — an authenticated caller
# could loop any of them with no server-side throttle, driving real
# OpenRouter cost. 20/minute is generous for normal interactive use, tight
# enough to block a scripted loop.
@router.post("/voice-script")
@limiter.limit("20/minute")
def voice_script(request: Request, body: LangReq, user: dict = Depends(require_user)):
    row = reference_data.get_latest_row(user["id"])
    if not row:
        raise HTTPException(status_code=404, detail="no readings")
    return content_llm.voice_agent(reference_data.row_to_reading(row), body.lang)


@router.post("/report")
@limiter.limit("20/minute")
def report(request: Request, body: LangReq, user: dict = Depends(require_user)):
    row = reference_data.get_latest_row(user["id"])
    if not row:
        raise HTTPException(status_code=404, detail="no readings")
    return content_llm.report_agent(reference_data.row_to_reading(row), reference_data.get_context(user["id"]), user["id"], body.lang)


@router.post("/self-care")
@limiter.limit("20/minute")
def self_care(request: Request, body: SelfCareReq, user: dict = Depends(require_user)):
    if not body.force:
        existing = reference_data.get_self_care_plan(user["id"])
        if existing:
            return existing

    row = reference_data.get_latest_row(user["id"])
    if not row:
        raise HTTPException(status_code=404, detail="no readings")
    reading = reference_data.row_to_reading(row)
    ctx = reference_data.get_context(user["id"])
    history = reference_data.get_chat_history(user["id"])
    return content_llm.self_care_agent(reading, ctx, history, user["id"], body.lang)


@router.get("/chat")
def get_chat(user: dict = Depends(require_user)):
    return {"messages": reference_data.get_chat_history(user["id"]), "context": reference_data.get_context(user["id"])}


@router.post("/chat")
@limiter.limit("30/minute")
def send_chat(request: Request, body: ChatSendReq, user: dict = Depends(require_user)):
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="empty message")

    now = datetime.now(timezone.utc)
    db.execute(
        "INSERT INTO chat_messages (user_id, role, content, lang, created_at) VALUES (%s, 'user', %s, %s, %s)",
        (user["id"], message, body.lang, now),
    )

    # Deterministic emergency backstop (2026-08-26) — checked before the
    # website chat coach gets a turn, same shared logic/phrase list the
    # WhatsApp agent uses (see core/emergency.py). Previously this surface
    # had nothing but a system-prompt line ("never give a diagnosis") — a
    # patient typing something like "I want to hurt myself" here got
    # whatever the model happened to produce, no code-level safety net.
    if emergency.is_emergency_message(message):
        reply_text = emergency.reply(body.lang)
        db.execute(
            "INSERT INTO chat_messages (user_id, role, content, lang, created_at) VALUES (%s, 'assistant', %s, %s, %s)",
            (user["id"], reply_text, body.lang, datetime.now(timezone.utc)),
        )
        return {
            "reply": reply_text,
            "context": reference_data.get_context(user["id"]),
            "contextChanged": False,
            "planChanged": False,
            "source": "emergency",
        }

    row = reference_data.get_latest_row(user["id"])
    reading = reference_data.row_to_reading(row) if row else None
    ctx = reference_data.get_context(user["id"])
    history = reference_data.get_chat_history(user["id"])

    # content_llm.chat_agent is now a real tool-calling agent: any patient-context
    # or diet-plan edits it decides to make are persisted by its own tools as
    # they happen, not applied here from a returned blob — this endpoint just
    # records the transcript and reports back what changed.
    out = content_llm.chat_agent(history, reading, ctx, user["id"], body.lang)

    db.execute(
        "INSERT INTO chat_messages (user_id, role, content, lang, created_at) VALUES (%s, 'assistant', %s, %s, %s)",
        (user["id"], out["reply"], body.lang, datetime.now(timezone.utc)),
    )

    return {
        "reply": out["reply"],
        "context": reference_data.get_context(user["id"]),
        "contextChanged": bool(out.get("contextChanged")),
        "planChanged": bool(out.get("planChanged")),
        "source": out.get("source"),
    }


@router.delete("/chat")
def reset_chat(user: dict = Depends(require_user)):
    db.execute("DELETE FROM chat_messages WHERE user_id = %s", (user["id"],))
    return {"ok": True}
