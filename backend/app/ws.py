"""Public WebSocket broadcast hub for /ws/pipeline.

Feeds a marketing-homepage diagram that visualizes two independent live
agents: Guidance Agent (core/guidance_agent.py, `source: "device"` events)
and WhatsApp Agent (core/whatsapp_agent.py + core/scheduler.py, `source:
"whatsapp"` events). No auth (this is a public, unauthenticated endpoint by
design) — every producer is responsible for keeping broadcast payloads free
of PII and raw biomarker values (phone numbers, patient names, message
content, biomarker values never belong here — only node/status/coarse-label
info, same discipline guidance_agent.py already established).

Minimal by design: a module-level set of connections, connect/disconnect,
and a broadcast that drops any socket that errors on send (client already
gone) instead of raising.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)

_connections: set[WebSocket] = set()

# WhatsApp Agent's actual work runs inside asyncio.to_thread() worker
# threads (see core/whatsapp_agent.py, core/scheduler.py) — those threads
# have no event loop of their own, so they can't `await broadcast()`
# directly. main.py's startup handler (guaranteed to run on the real running
# loop) registers it here once via set_loop(), and broadcast_from_thread()
# below bridges a worker thread's call back onto that loop safely.
_loop: Optional[asyncio.AbstractEventLoop] = None


def set_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


async def connect(ws: WebSocket) -> None:
    await ws.accept()
    _connections.add(ws)


async def disconnect(ws: WebSocket) -> None:
    _connections.discard(ws)


async def broadcast(event: dict[str, Any]) -> None:
    if not _connections:
        return
    payload = json.dumps(event, ensure_ascii=False)
    dead: list[WebSocket] = []
    for conn in list(_connections):
        try:
            await conn.send_text(payload)
        except Exception:
            dead.append(conn)
    for conn in dead:
        _connections.discard(conn)


def broadcast_from_thread(event: dict[str, Any]) -> None:
    """Sync-safe entry point for callers running inside asyncio.to_thread()
    worker threads (WhatsApp Agent's tool-calling loop and the scheduler's
    trigger dispatch). Schedules the real async broadcast() onto the main
    event loop via run_coroutine_threadsafe and blocks this thread only
    until it's queued/sent — never raises out to the caller (a broadcast
    failure must never break an actual patient-facing WhatsApp action)."""
    if _loop is None:
        logger.warning("ws.broadcast_from_thread: no event loop registered yet, dropping event %r", event.get("type"))
        return
    try:
        future = asyncio.run_coroutine_threadsafe(broadcast(event), _loop)
        future.result(timeout=5)
    except Exception:
        logger.exception("ws.broadcast_from_thread: failed to deliver event %r", event.get("type"))
