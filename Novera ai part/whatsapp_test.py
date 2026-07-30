"""Minimal standalone Meta WhatsApp Cloud API webhook — for isolated testing.

Run:  uvicorn whatsapp_test:app --port 8000
Then point your Meta Callback URL at  https://<ngrok>/whatsapp  with the same
verify token you set in VERIFY_TOKEN below. It just logs inbound messages.
"""
import json
import os

from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse

VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "novera_verify_123")

app = FastAPI()


@app.get("/")
def health_check() -> dict[str, str]:
    return {"status": "NOVERA WhatsApp service is running"}


@app.get("/whatsapp")
def verify(request: Request):
    p = request.query_params
    if p.get("hub.mode") == "subscribe" and p.get("hub.verify_token") == VERIFY_TOKEN:
        return PlainTextResponse(p.get("hub.challenge", ""))
    return PlainTextResponse("verification failed", status_code=403)


@app.post("/whatsapp")
async def webhook(request: Request) -> Response:
    data = json.loads(await request.body() or b"{}")
    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            for msg in change.get("value", {}).get("messages", []):
                text = (msg.get("text") or {}).get("body", "")
                print(f"Message from {msg.get('from')}: {text}")
    return Response(content='{"status":"ok"}', media_type="application/json")
