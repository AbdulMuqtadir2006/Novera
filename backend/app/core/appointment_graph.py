"""LangGraph appointment agent — the local WhatsApp-reply simulator
(`POST /api/appointment/reply`), used by the Appointments page's reply box.

    understand_reply -> (confirm?) -> book_slot -> compose_reply

The LLM only classifies intent (with a deterministic keyword fallback); the
actual booking always goes through core/booking.py (Postgres, double-booking
safe) — the LLM never invents a date or writes to the database (req 13).
"""
from __future__ import annotations

from typing import Any, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from . import booking, whatsapp_client
from .content_llm import LLMError, structured_json_call
from ..schemas import AppointmentReplyIntent

CONFIRM_WORDS = {"ok", "okay", "yes", "yep", "yeah", "sure", "confirm", "book", "go", "done", "نعم", "تمام", "موافق", "احجز"}
DECLINE_WORDS = {"no", "nope", "skip", "cancel", "later", "not now", "لا", "لاحقا", "الغاء"}
RESCHEDULE_WORDS = {"reschedule", "change", "another", "different", "move", "تغيير", "تأجيل"}


class ApptState(TypedDict, total=False):
    message: str
    lang: str
    intent: str
    booking: Optional[dict[str, Any]]
    reply: str


def keyword_intent(message: str) -> str:
    text = message.strip().lower()
    if any(w in text for w in RESCHEDULE_WORDS):
        return "reschedule"
    if any(text == w or text.startswith(w + " ") or w in text.split() for w in CONFIRM_WORDS):
        return "confirm"
    if any(text == w or w in text.split() for w in DECLINE_WORDS):
        return "decline"
    return "unknown"


def _understand(state: ApptState) -> ApptState:
    message = state["message"]
    lang = state.get("lang", "en")
    try:
        out = structured_json_call(
            system=(
                "You classify a patient's short WhatsApp reply about booking a clinic appointment. "
                "intent is one of: confirm (they agree to book), decline (they say no), reschedule "
                "(they want a different time), question (they ask something), unknown."
            ),
            user=f"Patient reply ({lang}): {message!r}",
            model_cls=AppointmentReplyIntent,
            max_tokens=200,
            temperature=0.0,
        )
        return {"intent": out.intent}
    except LLMError as exc:
        print(f"[appointment.understand] fallback: {exc}")
        return {"intent": keyword_intent(message)}


def _route(state: ApptState) -> str:
    return "book" if state.get("intent") == "confirm" else "respond"


def _book(state: ApptState) -> ApptState:
    result = booking.find_and_book_slot(user_id=None, phone=None, channel="whatsapp")
    return {"booking": result}


def _respond(state: ApptState) -> ApptState:
    intent = state.get("intent", "unknown")
    lang = state.get("lang", "en")
    if intent == "confirm" and state.get("booking"):
        return {"reply": whatsapp_client.confirmation_message(state["booking"])}
    if intent == "decline":
        return {"reply": (
            "No problem — I won't book anything. You can message me any time and I'll set it up."
            if lang != "ar" else "لا مشكلة — لن أحجز شيئاً. راسلني في أي وقت وسأرتب الموعد."
        )}
    if intent == "reschedule":
        from .. import config
        return {"reply": (
            f"Sure — tell me a day and time that suits you and I'll rebook at {config.CLINIC_NAME}, {config.CLINIC_BRANCH}."
            if lang != "ar" else f"بالطبع — أخبرني باليوم والوقت المناسب وسأعيد الحجز في {config.CLINIC_NAME}، {config.CLINIC_BRANCH}."
        )}
    return {"reply": whatsapp_client.offer_message()}


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


def handle_reply(message: str, lang: str = "en") -> dict[str, Any]:
    final = _graph().invoke({"message": message, "lang": lang})
    return {"reply": final.get("reply", ""), "intent": final.get("intent"), "booking": final.get("booking")}


def send_offer(to: Optional[str] = None, case_id: Optional[str] = None, simulate: bool = False) -> dict[str, Any]:
    body = whatsapp_client.offer_message(case_id)
    result = whatsapp_client.send_message(body, to=to, simulate=simulate)
    return {"message": body, "delivery": result}
