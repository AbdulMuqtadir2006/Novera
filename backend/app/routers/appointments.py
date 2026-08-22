from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .. import db
from ..core import appointment_graph, booking, clinic
from ..deps import require_user
from ..schemas import OfferReq, ReplyReq
from ..security import normalize_phone

router = APIRouter()


@router.get("/clinic")
def get_clinic(user: dict = Depends(require_user)):
    return clinic.location()


@router.post("/appointment/offer")
def appointment_offer(body: OfferReq, user: dict = Depends(require_user)):
    # Bug fix (2026-08-22): used to fall back to client-supplied body.to
    # whenever the caller's own account had no phone on file, letting any
    # authenticated user direct a real WhatsApp send at an arbitrary number
    # they don't own. Only ever send to the caller's own registered phone —
    # send_offer's own to=None handling already falls back to config.WHATSAPP_TO
    # (a fixed test recipient) if this account has none, same as before.
    phone = user.get("phone")
    to = normalize_phone(phone) if phone else None
    case_row = db.fetch_one("SELECT case_id FROM screening_cases WHERE user_id = %s ORDER BY id DESC LIMIT 1", (user["id"],))
    case_id = case_row["case_id"] if case_row else None
    try:
        result = appointment_graph.send_offer(to=to, case_id=case_id, simulate=body.simulate)
    except Exception as exc:
        print(f"[appointments] send_offer failed: {exc}")
        raise HTTPException(status_code=502, detail="Could not send the appointment offer. Try again.")
    return {**result, "sentTo": to}


@router.post("/appointment/reply")
def appointment_reply(body: ReplyReq, user: dict = Depends(require_user)):
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="empty message")
    try:
        phone = normalize_phone(user["phone"]) if user.get("phone") else None
        return appointment_graph.handle_reply(message, body.lang, user_id=user["id"], phone=phone)
    except Exception as exc:
        print(f"[appointments] handle_reply failed: {exc}")
        raise HTTPException(status_code=502, detail="Could not process the reply. Try again.")


@router.get("/appointment/bookings")
def bookings(user: dict = Depends(require_user)):
    return {"bookings": booking.list_bookings_for_user(user["id"])}
