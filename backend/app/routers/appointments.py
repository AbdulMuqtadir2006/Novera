from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from .. import db
from ..core import appointment_graph, booking, clinic
from ..deps import get_current_user
from ..schemas import OfferReq, ReplyReq
from ..security import normalize_phone

router = APIRouter()


@router.get("/clinic")
def get_clinic():
    return clinic.location()


@router.post("/appointment/offer")
def appointment_offer(body: OfferReq, user: Optional[dict] = Depends(get_current_user)):
    phone = (user or {}).get("phone") or body.to
    to = normalize_phone(phone) if phone else None
    case_row = db.fetch_one("SELECT case_id FROM screening_cases ORDER BY id DESC LIMIT 1")
    case_id = case_row["case_id"] if case_row else None
    try:
        result = appointment_graph.send_offer(to=to, case_id=case_id, simulate=body.simulate)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {**result, "sentTo": to}


@router.post("/appointment/reply")
def appointment_reply(body: ReplyReq):
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="empty message")
    try:
        return appointment_graph.handle_reply(message, body.lang)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/appointment/bookings")
def bookings():
    return {"bookings": booking.list_bookings()}
