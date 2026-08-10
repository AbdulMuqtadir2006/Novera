from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from .. import db
from ..core import content_llm, reference_data
from ..deps import require_user
from ..schemas import ChatSendReq, LangReq

router = APIRouter()


@router.post("/voice-script")
def voice_script(body: LangReq, user: dict = Depends(require_user)):
    row = reference_data.get_latest_row()
    if not row:
        raise HTTPException(status_code=404, detail="no readings")
    return content_llm.voice_agent(reference_data.row_to_reading(row), body.lang)


@router.post("/report")
def report(body: LangReq, user: dict = Depends(require_user)):
    row = reference_data.get_latest_row()
    if not row:
        raise HTTPException(status_code=404, detail="no readings")
    return content_llm.report_agent(reference_data.row_to_reading(row), reference_data.get_context(), body.lang)


@router.post("/self-care")
def self_care(body: LangReq, user: dict = Depends(require_user)):
    row = reference_data.get_latest_row()
    if not row:
        raise HTTPException(status_code=404, detail="no readings")
    reading = reference_data.row_to_reading(row)
    ctx = reference_data.get_context()
    history = reference_data.get_chat_history()
    return content_llm.self_care_agent(reading, ctx, history, body.lang)


@router.get("/chat")
def get_chat(user: dict = Depends(require_user)):
    return {"messages": reference_data.get_chat_history(), "context": reference_data.get_context()}


@router.post("/chat")
def send_chat(body: ChatSendReq, user: dict = Depends(require_user)):
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="empty message")

    now = datetime.now(timezone.utc)
    db.execute(
        "INSERT INTO chat_messages (role, content, lang, created_at) VALUES ('user', %s, %s, %s)",
        (message, body.lang, now),
    )

    row = reference_data.get_latest_row()
    reading = reference_data.row_to_reading(row) if row else None
    ctx = reference_data.get_context()
    history = reference_data.get_chat_history()

    out = content_llm.chat_agent(history, reading, ctx, body.lang)

    db.execute(
        "INSERT INTO chat_messages (role, content, lang, created_at) VALUES ('assistant', %s, %s, %s)",
        (out["reply"], body.lang, datetime.now(timezone.utc)),
    )

    if out.get("contextChanged"):
        db.execute(
            """
            UPDATE patient_context
            SET diagnosis = %s, medications = %s, notes = %s, updated_at = %s
            WHERE id = 1
            """,
            (out.get("diagnosis", ""), out.get("medications", ""), out.get("notes", ""), datetime.now(timezone.utc)),
        )

    return {
        "reply": out["reply"],
        "context": reference_data.get_context(),
        "contextChanged": bool(out.get("contextChanged")),
        "source": out.get("source"),
    }


@router.delete("/chat")
def reset_chat(user: dict = Depends(require_user)):
    db.execute("DELETE FROM chat_messages")
    return {"ok": True}
