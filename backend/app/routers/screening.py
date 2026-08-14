from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ..core import scoring, screening_llm
from ..deps import require_user

router = APIRouter()


def _claim_new_screening_case():
    """Shared setup for both /predict-organ and /predict-organ/stream: turn the
    dashboard's latest reading into a claimed 'PROCESSING' screening_cases row.
    Thin HTTP wrapper over scoring.claim_new_case_from_latest_reading(), which
    is also reused (unmodified) by the autonomous guidance agent — see
    core/guidance_agent.py and core/scoring.py's docstring on that function."""
    case_row = scoring.claim_new_case_from_latest_reading()
    if not case_row:
        raise HTTPException(status_code=404, detail="no readings")
    return case_row


@router.post("/predict-organ")
def predict_organ(user: dict = Depends(require_user)):
    """Deep AI analysis: runs the deterministic screening pipeline
    (reference-range score + similarity score + exactly one OpenRouter call,
    req 5) on the dashboard's latest reading, and persists it as a real
    screening_cases row so future similarity scoring benefits from it."""
    case_row = _claim_new_screening_case()
    result = screening_llm.process_case(case_row)

    if result["status"] != "PROCESSED":
        # OpenRouter failed or the reading didn't validate — never a fake reason (req 8).
        raise HTTPException(status_code=502, detail=result)

    return {
        "prediction": result["ai_prediction"],
        "confidence": result["ai_confidence"],
        "reason": result["ai_reason"],
        "source": "ai",
        "case_id": result["case_id"],
        "specialist_results": result["specialist_results"],
    }


@router.post("/predict-organ/stream")
def predict_organ_stream(user: dict = Depends(require_user)):
    """Same pipeline as /predict-organ, streamed as Server-Sent Events — one
    real event per pipeline step (validate, score per organ, decide,
    persist/release) as it actually happens, for a workflow visualizer driven
    by genuine backend progress instead of a decorative timer loop. A plain
    POST (not a native EventSource GET) so the existing Bearer-token fetch
    helper works unchanged; the frontend reads the streamed body directly."""
    case_row = _claim_new_screening_case()

    def event_source():
        for event in screening_llm.process_case_stream(case_row):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream")
