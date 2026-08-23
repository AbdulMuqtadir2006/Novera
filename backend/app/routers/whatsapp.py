"""Meta WhatsApp Cloud API webhook — GET verifies, POST handles inbound
messages (req 10). Mounted at the bare /webhook path (no /api prefix) so the
Meta dashboard's Callback URL is simply https://api.<domain>/webhook.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Request, Response
from fastapi.responses import PlainTextResponse

from .. import config, db
from ..core import whatsapp_agent, whatsapp_client

logger = logging.getLogger(__name__)

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


def _already_processed(message_id: str) -> bool:
    """Claims a Meta message id via INSERT ... ON CONFLICT DO NOTHING —
    returns True if it was already claimed before (a webhook retry), False
    if this call just claimed it (a genuinely new message)."""
    row = db.fetch_one(
        "INSERT INTO whatsapp_inbound_messages (message_id) VALUES (%s) "
        "ON CONFLICT (message_id) DO NOTHING RETURNING message_id",
        (message_id,),
    )
    return row is None


def _process_and_reply(from_number: str, text: str) -> None:
    """Runs the (potentially slow — LLM calls, PDF generation) agent loop and
    sends the reply. Called as a background task so the webhook itself can
    ack Meta immediately, rather than risk Meta timing out and retrying the
    same inbound message while this is still running."""
    try:
        reply = whatsapp_agent.handle_inbound(from_number, text, lang="en")
        # handle_inbound can return "" (2026-08-23 dup-message fix) when a
        # self-sending tool (e.g. send_report_pdf) already messaged the
        # patient directly this run — sending `reply` too would double-send.
        if reply:
            whatsapp_client.send_message(reply, to=from_number)
    except Exception:
        logger.exception("whatsapp webhook: background processing failed for from=%s", from_number)


@router.post("/webhook")
async def inbound(request: Request, background_tasks: BackgroundTasks) -> Response:
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
                message_id = msg.get("id")
                if message_id and _already_processed(message_id):
                    # Meta re-delivering a message we've already started/finished
                    # handling (it retries when we don't ack fast enough) — skip
                    # it rather than replaying the agent loop (and any PDF send)
                    # a second time.
                    logger.info("whatsapp webhook: skipping duplicate message_id=%s", message_id)
                    continue
                background_tasks.add_task(_process_and_reply, from_number, text)

    # Ack immediately — the actual reply (LLM loop, possible PDF generation +
    # send) runs in the background so Meta never waits long enough to retry.
    return Response(content='{"status":"ok"}', media_type="application/json")
