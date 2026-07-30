from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import db
from ..core import reference_data, scoring, screening_llm

router = APIRouter()

CREATININE_MGDL_TO_UMOLL = 88.42


@router.post("/predict-organ")
def predict_organ():
    """Deep AI analysis: runs the deterministic screening pipeline
    (reference-range score + similarity score + exactly one OpenRouter call,
    req 5) on the dashboard's latest reading, and persists it as a real
    screening_cases row so future similarity scoring benefits from it."""
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
