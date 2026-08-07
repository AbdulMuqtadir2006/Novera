from __future__ import annotations

from fastapi import APIRouter

from .. import config, db

router = APIRouter()


@router.get("/api/health")
def health() -> dict:
    try:
        readings = db.fetch_one("SELECT COUNT(*) AS c FROM readings")
        db_ok = True
    except Exception:
        readings, db_ok = None, False
    return {
        "ok": True,
        "db_ok": db_ok,
        "ai_enabled": config.AI_ENABLED,
        "whatsapp_enabled": config.WHATSAPP_ENABLED,
        "model_content": config.OPENROUTER_MODEL_CONTENT,
        "model_screening": config.OPENROUTER_MODEL_SCREENING,
        "readings": readings["c"] if readings else None,
    }
