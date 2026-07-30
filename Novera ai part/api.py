"""NOVERA agentic AI service (FastAPI).

Exposes every agent over HTTP so the web/Node backend and frontend can use one
LangGraph-driven brain: report, voice, self-care, doctor-context chat, organ
prediction, and the WhatsApp appointment agent (with a local simulator).

Run:  uvicorn api:app --port 8000
"""
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Optional

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from novera_ai import agents, appointment, clinic, config, whatsapp
from novera_ai.orchestrator import db as orch_db
from novera_ai.orchestrator.graph import run_pipeline, run_whatsapp_reply

app = FastAPI(title="NOVERA Agentic AI", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- request models (lenient: reading/context are passthrough dicts) ----
class VoiceReq(BaseModel):
    reading: dict[str, Any]
    lang: str = "en"


class ReportReq(BaseModel):
    reading: dict[str, Any]
    context: dict[str, Any] = {}
    lang: str = "en"


class SelfCareReq(BaseModel):
    reading: dict[str, Any]
    context: dict[str, Any] = {}
    chat: list[dict[str, Any]] = []
    lang: str = "en"


class ChatReq(BaseModel):
    messages: list[dict[str, Any]]
    reading: Optional[dict[str, Any]] = None
    context: dict[str, Any] = {}
    lang: str = "en"


class PredictReq(BaseModel):
    reading: dict[str, Any]


class OfferReq(BaseModel):
    to: Optional[str] = None
    case_id: Optional[str] = None
    simulate: bool = False


class ReplyReq(BaseModel):
    message: str
    lang: str = "en"


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "ai_enabled": config.AI_ENABLED,
        "whatsapp_enabled": config.WHATSAPP_ENABLED,
        "model": config.RESOLVED_MODEL,
    }


# ---- agentic orchestrator (LangGraph pipeline) ----
class PipelineReq(BaseModel):
    user_id: str = "demo-user"
    raw_reading: dict[str, Any]


class WhatsAppReplyReq(BaseModel):
    user_id: str = "demo-user"
    message: str


@app.post("/orchestrator/run")
def orchestrator_run(req: PipelineReq) -> dict[str, Any]:
    return run_pipeline(req.user_id, req.raw_reading)


@app.post("/orchestrator/whatsapp")
def orchestrator_whatsapp(req: WhatsAppReplyReq) -> dict[str, Any]:
    return run_whatsapp_reply(req.user_id, req.message)


@app.get("/orchestrator/user/{user_id}")
def orchestrator_user(user_id: str) -> dict[str, Any]:
    orch_db.init_db()
    return {"user": orch_db.get_user(user_id), "outputs": orch_db.list_outputs(user_id, 10)}


@app.get("/orchestrator/slots")
def orchestrator_slots() -> dict[str, Any]:
    orch_db.init_db()
    return {"slots": orch_db.get_open_slots(10)}


@app.get("/orchestrator/report/{reading_id}")
def orchestrator_report(reading_id: str):
    path = orch_db.config.PROJECT_ROOT / "novera_ai" / "orchestrator" / "reports" / f"novera-{reading_id}.pdf"
    if not path.exists():
        return Response(status_code=404, content="report not found")
    return FileResponse(str(path), media_type="application/pdf", filename=f"novera-{reading_id}.pdf")


@app.get("/clinic")
def get_clinic() -> dict[str, Any]:
    return clinic.location()


# ---- content agents ----
@app.post("/ai/voice")
def voice(req: VoiceReq) -> dict[str, Any]:
    return agents.voice_agent(req.reading, req.lang)


@app.post("/ai/report")
def report(req: ReportReq) -> dict[str, Any]:
    return agents.report_agent(req.reading, req.context, req.lang)


@app.post("/ai/self-care")
def self_care(req: SelfCareReq) -> dict[str, Any]:
    return agents.self_care_agent(req.reading, req.context, req.chat, req.lang)


@app.post("/ai/chat")
def chat(req: ChatReq) -> dict[str, Any]:
    return agents.chat_agent(req.messages, req.reading, req.context, req.lang)


@app.post("/ai/predict-organ")
def predict_organ(req: PredictReq) -> dict[str, Any]:
    return agents.predict_organ(req.reading)


# ---- appointment / whatsapp ----
@app.post("/appointment/offer")
def appointment_offer(req: OfferReq) -> dict[str, Any]:
    return appointment.send_offer(to=req.to, case_id=req.case_id, simulate=req.simulate)


@app.post("/appointment/reply")
def appointment_reply(req: ReplyReq) -> dict[str, Any]:
    """Local simulator for the inbound WhatsApp reply — no Twilio needed."""
    return appointment.handle_reply(req.message, req.lang)


@app.get("/appointment/bookings")
def appointment_bookings() -> dict[str, Any]:
    return {"bookings": appointment.list_bookings()}


@app.get("/whatsapp/webhook")
def whatsapp_verify(request: Request):
    """Meta webhook verification handshake. Echoes hub.challenge if the token matches."""
    params = request.query_params
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == config.META_VERIFY_TOKEN:
        return PlainTextResponse(params.get("hub.challenge", ""))
    return PlainTextResponse("verification failed", status_code=403)


def _valid_signature(raw: bytes, header: str) -> bool:
    """Verify Meta's X-Hub-Signature-256 header against the app secret."""
    if not config.META_APP_SECRET:
        return True  # signature checking disabled when no app secret is set
    expected = "sha256=" + hmac.new(config.META_APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header or "")


@app.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request) -> Response:
    """Meta inbound WhatsApp webhook.

    Meta delivers messages as JSON and expects a fast 200. We ack, then run the
    appointment agent and push the reply back out via the Graph API (separate
    call — unlike Twilio, the reply is not part of this HTTP response).
    """
    raw = await request.body()
    if not _valid_signature(raw, request.headers.get("X-Hub-Signature-256", "")):
        return Response(status_code=403, content="bad signature")

    data = json.loads(raw or b"{}")
    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []):
                if msg.get("type") != "text":
                    continue
                from_number = msg.get("from", "")
                text = (msg.get("text") or {}).get("body", "").strip()
                if not (from_number and text):
                    continue
                result = appointment.handle_reply(text, lang="en")
                whatsapp.send_message(result["reply"], to=from_number)

    return Response(content='{"status":"ok"}', media_type="application/json")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=config.SERVICE_PORT)
