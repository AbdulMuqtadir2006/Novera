"""Meta WhatsApp Cloud API webhook — GET verifies, POST handles inbound
messages (req 10). Mounted at the bare /webhook path (no /api prefix) so the
Meta dashboard's Callback URL is simply https://api.<domain>/webhook.
"""
from __future__ import annotations

import hashlib
import hmac
import json

from fastapi import APIRouter, Request, Response
from fastapi.responses import PlainTextResponse

from .. import config
from ..core import whatsapp_agent, whatsapp_client

router = APIRouter()


@router.get("/webhook")
def verify(request: Request):
    params = request.query_params
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == config.META_VERIFY_TOKEN:
        return PlainTextResponse(params.get("hub.challenge", ""))
    return PlainTextResponse("verification failed", status_code=403)


def _valid_signature(raw: bytes, header: str) -> bool:
    if not config.META_APP_SECRET:
        # Fail closed: with no app secret configured, authenticity can't be
        # verified at all, so reject rather than silently trust everything.
        return False
    expected = "sha256=" + hmac.new(config.META_APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header or "")


@router.post("/webhook")
async def inbound(request: Request) -> Response:
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
                reply = whatsapp_agent.handle_inbound(from_number, text, lang="en")
                whatsapp_client.send_message(reply, to=from_number)

    return Response(content='{"status":"ok"}', media_type="application/json")
