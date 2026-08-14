"""NOVERA backend — FastAPI entry point (app.main:app).

Consolidates what used to be a Node/Express backend + a separate Python
LangGraph service into one FastAPI app on Postgres.
"""
from __future__ import annotations

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from . import config, ws
from .core import scoring
from .rate_limit import limiter
from .routers import appointments, auth, content_agents, device, health, patient_context, readings, screening, whatsapp

app = FastAPI(title="NOVERA API", version="1.0.0")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    # Cache reference ranges once at boot (req 9) instead of hitting Postgres
    # on every screening request.
    try:
        scoring.load_reference_ranges()
    except Exception as exc:
        print(f"[startup] reference range cache not warmed (DB not ready yet?): {exc}")


app.include_router(health.router)
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(readings.router, prefix="/api", tags=["readings"])
app.include_router(device.router, prefix="/api", tags=["device"])
app.include_router(patient_context.router, prefix="/api", tags=["patient-context"])
app.include_router(content_agents.router, prefix="/api", tags=["ai"])
app.include_router(screening.router, prefix="/api", tags=["screening"])
app.include_router(appointments.router, prefix="/api", tags=["appointments"])
app.include_router(whatsapp.router, tags=["whatsapp"])  # bare /webhook, per req 10


@app.websocket("/ws/pipeline")
async def pipeline_ws(websocket: WebSocket) -> None:
    """Public, unauthenticated feed for the guidance agent's live pipeline
    diagram (app/ws.py + core/guidance_agent.py). Client -> server messages
    aren't part of the contract; we just read and discard them so the
    connection's read loop can detect disconnects."""
    await ws.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await ws.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=config.SERVICE_PORT)
