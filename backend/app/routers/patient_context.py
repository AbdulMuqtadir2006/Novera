from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from .. import db
from ..core import reference_data
from ..schemas import PatientContextIn

router = APIRouter()


@router.get("/patient-context")
def get_context():
    return reference_data.get_context()


@router.post("/patient-context")
def save_context(body: PatientContextIn):
    db.execute(
        """
        UPDATE patient_context
        SET diagnosis = %s, medications = %s, notes = %s, updated_at = %s
        WHERE id = 1
        """,
        (body.diagnosis, body.medications, body.notes, datetime.now(timezone.utc)),
    )
    return reference_data.get_context()
