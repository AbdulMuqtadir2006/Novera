from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from .. import db
from ..core import content_llm, reference_data
from ..deps import require_user
from ..schemas import ChatSendReq, LangReq, SelfCareReq

router = APIRouter()


@router.post("/voice-script")
def voice_script(body: LangReq, user: dict = Depends(require_user)):
    row = reference_data.get_latest_row(user["id"])
    if not row:
        raise HTTPException(status_code=404, detail="no readings")
    return content_llm.voice_agent(reference_data.row_to_reading(row), body.lang)


@router.post("/report")
def report(body: LangReq, user: dict = Depends(require_user)):
    row = reference_data.get_latest_row(user["id"])
    if not row:
        raise HTTPException(status_code=404, detail="no readings")
    return content_llm.report_agent(reference_data.row_to_reading(row), reference_data.get_context(user["id"]), user["id"], body.lang)


@router.post("/self-care")
def self_care(body: SelfCareReq, user: dict = Depends(require_user)):
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
def send_chat(body: ChatSendReq, user: dict = Depends(require_user)):
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="empty message")

    now = datetime.now(timezone.utc)
    db.execute(
        "INSERT INTO chat_messages (user_id, role, content, lang, created_at) VALUES (%s, 'user', %s, %s, %s)",
        (user["id"], message, body.lang, now),
    )

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
