"""LangGraph wiring (brief §8): the main screening graph + the WhatsApp-reply
re-entry graph. Fixed edges where the next step never changes; agentic edges at
the real decision points; a hardcoded Python threshold gate.

Deviation (intentional): the threshold gate runs after the outputs are generated
(report included) rather than immediately after analysis, so the report exists
when the WhatsApp reply asks to "receive your report". `threshold_crossed` is
still set only by the Python gate inside the Analysis node.
"""
from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from . import agents, db
from .state import NoveraState


def _build_main():
    g = StateGraph(NoveraState)
    g.add_node("capture", agents.capture_agent)
    g.add_node("qa", agents.confidence_qa_agent)
    g.add_node("orchestrator", agents.orchestrator_node)
    g.add_node("analysis", agents.analysis_agent)
    g.add_node("insight", agents.insight_agent)
    g.add_node("guidance", agents.guidance_agent)
    g.add_node("voice", agents.voice_agent)
    g.add_node("report", agents.report_agent)
    g.add_node("whatsapp_notifier", agents.whatsapp_notifier_agent)

    g.set_entry_point("capture")
    g.add_edge("capture", "qa")
    g.add_edge("qa", "orchestrator")
    # Agentic edge #1 — the Boss decides proceed vs. loop back.
    g.add_conditional_edges("orchestrator", agents.orchestrator_route_after_qa,
                            {"analysis": "analysis", "capture": "capture"})
    # Fixed pipeline of outputs.
    g.add_edge("analysis", "insight")
    g.add_edge("insight", "guidance")
    g.add_edge("guidance", "voice")
    g.add_edge("voice", "report")
    # Hardcoded safety gate — pure Python if/else.
    g.add_conditional_edges("report", agents.threshold_gate,
                            {"escalate": "whatsapp_notifier", "proceed": END})
    g.add_edge("whatsapp_notifier", END)
    return g.compile()


def _build_whatsapp():
    g = StateGraph(NoveraState)
    g.add_node("multi_language", agents.multi_language_agent)
    g.add_node("appointment_booking", agents.appointment_booking_agent)
    g.add_node("report_delivery", agents.report_delivery_agent)
    g.add_node("explain_more", agents.explain_more_agent)

    g.set_entry_point("multi_language")
    # Agentic edge #2 — language + intent in one call, then route.
    g.add_conditional_edges("multi_language", agents.route_whatsapp_intent, {
        "book_appointment": "appointment_booking",
        "send_report": "report_delivery",
        "explain_more": "explain_more",
        "decline": END,
    })
    g.add_edge("appointment_booking", END)
    g.add_edge("report_delivery", END)
    g.add_edge("explain_more", END)
    return g.compile()


# Compiled graphs (also exported for LangGraph Studio via langgraph.json).
main_graph = _build_main()
whatsapp_graph = _build_whatsapp()


# ---- public run helpers ----
def run_pipeline(user_id: str, raw_reading: dict) -> dict[str, Any]:
    db.init_db()
    final = main_graph.invoke({"user_id": user_id, "raw_reading": raw_reading, "trace": []})
    return _summarize(final)


def run_whatsapp_reply(user_id: str, message: str) -> dict[str, Any]:
    db.init_db()
    state = db.load_latest_state(user_id)
    if not state:
        return {"error": "No prior reading for this user. Run the pipeline first."}
    state["whatsapp_reply"] = message
    state["trace"] = []
    final = whatsapp_graph.invoke(state)
    return _summarize(final)


def _summarize(state: dict[str, Any]) -> dict[str, Any]:
    """Trim internal keys for a clean API response, keep the observable trace."""
    keys = (
        "user_id", "reading_id", "confidence_score", "confidence_reason", "qa_loop_count", "qa_passed",
        "analysis_results", "flagged_domains", "threshold_crossed", "threshold_details",
        "insight_text", "guidance_plan", "voice_script", "report_path",
        "whatsapp_message_sent", "detected_language", "language_switched", "whatsapp_intent",
        "appointment_booked", "appointment_details", "trace", "error",
    )
    return {k: state[k] for k in keys if k in state}
