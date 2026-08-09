from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from .. import db
from ..core import reference_data, scoring, screening_llm

router = APIRouter()

CREATININE_MGDL_TO_UMOLL = 88.42


def _claim_new_screening_case():
    """Shared setup for both /predict-organ and /predict-organ/stream: turn the
    dashboard's latest reading into a claimed 'PROCESSING' screening_cases row."""
    row = reference_data.get_latest_row()
    if not row:
        raise HTTPException(status_code=404, detail="no readings")
    reading = reference_data.row_to_reading(row)
    m = reading["metrics"]

    case_id = scoring.add_reading(
        ph=float(m["ph"]["value"]),
        urea_mg_dl=float(m["urea"]["value"]),
        creatinine_umol_l=float(m["creatinine"]["value"]) * CREATININE_MGDL_TO_UMOLL,
        temperature_c=float(m["temperature"]["value"]),
    )
    case_row = db.fetch_one(
        """
        SELECT id, case_id, ph, urea_mg_dl, creatinine_umol_l, temperature_c, status
        FROM screening_cases WHERE case_id = %s
        """,
        (case_id,),
    )
    scoring.claim_reading(case_row["id"])
    case_row["status"] = "PROCESSING"
    return case_row


@router.post("/predict-organ")
def predict_organ():
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
def predict_organ_stream():
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
