from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from .. import db
from ..core import reference_data
from ..deps import require_user
from ..schemas import PatientContextIn

router = APIRouter()


@router.get("/patient-context")
def get_context(user: dict = Depends(require_user)):
    return reference_data.get_context(user["id"])


@router.post("/patient-context")
def save_context(body: PatientContextIn, user: dict = Depends(require_user)):
    db.execute(
        """
        INSERT INTO patient_context (user_id, diagnosis, medications, notes, updated_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET
            diagnosis = EXCLUDED.diagnosis, medications = EXCLUDED.medications,
            notes = EXCLUDED.notes, updated_at = EXCLUDED.updated_at
        """,
        (user["id"], body.diagnosis, body.medications, body.notes, datetime.now(timezone.utc)),
    )
    return reference_data.get_context(user["id"])
