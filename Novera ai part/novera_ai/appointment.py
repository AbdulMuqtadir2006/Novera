"""LangGraph appointment agent.

A real tool-using state machine:
    understand_reply → (confirm?) → book_slot → compose_reply

The LLM does natural-language understanding of the patient's WhatsApp reply
(with a deterministic keyword fallback); the scheduling/booking/location steps
are deterministic tools. This keeps it genuinely agentic yet reliable on free
models.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from . import clinic, config, whatsapp
from .llm import LLMError, structured_json_call
from .schemas import AppointmentReplyIntent

BOOKINGS_FILE = config.PROJECT_ROOT / "appointments.json"

CONFIRM_WORDS = {"ok", "okay", "yes", "yep", "yeah", "sure", "confirm", "book", "go", "done", "نعم", "تمام", "موافق", "احجز"}
DECLINE_WORDS = {"no", "nope", "skip", "cancel", "later", "not now", "لا", "لاحقا", "الغاء"}
RESCHEDULE_WORDS = {"reschedule", "change", "another", "different", "move", "تغيير", "تأجيل"}


class ApptState(TypedDict, total=False):
    message: str
    lang: str
    intent: str
    booking: Optional[dict[str, Any]]
    reply: str


def _keyword_intent(message: str) -> str:
    text = message.strip().lower()
    if any(w in text for w in RESCHEDULE_WORDS):
        return "reschedule"
    if any(text == w or text.startswith(w + " ") or w in text.split() for w in CONFIRM_WORDS):
        return "confirm"
    if any(text == w or w in text.split() for w in DECLINE_WORDS):
        return "decline"
    return "unknown"


# ---- graph nodes ----
def _understand(state: ApptState) -> ApptState:
    message = state["message"]
    lang = state.get("lang", "en")
    try:
        out = structured_json_call(
            system=(
                "You classify a patient's short WhatsApp reply about booking a clinic appointment. "
                "intent is one of: confirm (they agree to book), decline (they say no), reschedule "
                "(they want a different time), question (they ask something), unknown. Optionally capture a "
                "clinic name they mention."
            ),
            user=f"Patient reply ({lang}): {message!r}",
            model_cls=AppointmentReplyIntent,
            max_tokens=200,
            temperature=0.0,
        )
        return {"intent": out.intent}
    except LLMError as exc:
        print(f"[appointment.understand] fallback: {exc}")
        return {"intent": _keyword_intent(message)}


def _route(state: ApptState) -> str:
    return "book" if state.get("intent") == "confirm" else "respond"


def _book(state: ApptState) -> ApptState:
    slot = clinic.compute_slot(datetime.now())
    booking = {
        **slot,
        "location": clinic.location(),
        "booked_at": datetime.now().isoformat(timespec="seconds"),
        "channel": "whatsapp",
    }
    _persist_booking(booking)
    return {"booking": booking}


def _respond(state: ApptState) -> ApptState:
    intent = state.get("intent", "unknown")
    lang = state.get("lang", "en")
    if intent == "confirm" and state.get("booking"):
        return {"reply": whatsapp.confirmation_message(state["booking"])}
    if intent == "decline":
        return {"reply": (
            "No problem — I won't book anything. You can message me any time and I'll set it up."
            if lang != "ar" else
            "لا مشكلة — لن أحجز شيئاً. راسلني في أي وقت وسأرتب الموعد."
        )}
    if intent == "reschedule":
        return {"reply": (
            f"Sure — tell me a day and time that suits you and I'll rebook at {config.CLINIC_NAME}, {config.CLINIC_BRANCH}."
            if lang != "ar" else
            f"بالطبع — أخبرني باليوم والوقت المناسب وسأعيد الحجز في {config.CLINIC_NAME}، {config.CLINIC_BRANCH}."
        )}
    return {"reply": whatsapp.offer_message()}


def _build_graph():
    g = StateGraph(ApptState)
    g.add_node("understand", _understand)
    g.add_node("book", _book)
    g.add_node("respond", _respond)
    g.add_edge(START, "understand")
    g.add_conditional_edges("understand", _route, {"book": "book", "respond": "respond"})
    g.add_edge("book", "respond")
    g.add_edge("respond", END)
    return g.compile()


_GRAPH = None


def _graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = _build_graph()
    return _GRAPH


def _persist_booking(booking: dict[str, Any]) -> None:
    existing: list[dict[str, Any]] = []
    if BOOKINGS_FILE.exists():
        try:
            existing = json.loads(BOOKINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            existing = []
    existing.append(booking)
    BOOKINGS_FILE.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


# ---- public API ----
def handle_reply(message: str, lang: str = "en") -> dict[str, Any]:
    """Run the agent on an inbound reply; returns the reply text + any booking."""
    final = _graph().invoke({"message": message, "lang": lang})
    return {"reply": final.get("reply", ""), "intent": final.get("intent"), "booking": final.get("booking")}


def send_offer(to: Optional[str] = None, case_id: Optional[str] = None, simulate: bool = False) -> dict[str, Any]:
    body = whatsapp.offer_message(case_id)
    result = whatsapp.send_message(body, to=to, simulate=simulate)
    return {"message": body, "delivery": result}


def list_bookings() -> list[dict[str, Any]]:
    if BOOKINGS_FILE.exists():
        try:
            return json.loads(BOOKINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []
