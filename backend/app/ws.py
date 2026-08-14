"""Public WebSocket broadcast hub for /ws/pipeline.

Feeds a marketing-homepage diagram that visualizes the autonomous guidance
agent (core/guidance_agent.py) actually working in real time. No auth (this
is a public, unauthenticated endpoint by design) — which is exactly why
guidance_agent.py is the only producer of events here and is responsible for
keeping every broadcast payload free of PII and raw biomarker values.

Minimal by design: a module-level set of connections, connect/disconnect,
and a broadcast that drops any socket that errors on send (client already
gone) instead of raising.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import WebSocket

_connections: set[WebSocket] = set()


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
