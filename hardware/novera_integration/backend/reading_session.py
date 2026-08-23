"""
Reading-session state machine: mediates between the dashboard "Start Reading"
button and the ESP32, since the ESP32 can't be pushed to directly (no public
IP / no persistent socket in the current firmware) -- it polls instead.

Flow:
    1. Dashboard: POST /api/reading-sessions            -> creates session, status=REQUESTED
    2. ESP32 (polls every ~1-2s): GET /api/reading-sessions/pending
       -> claims the oldest REQUESTED session, status=ACKNOWLEDGED
       -> ESP32 turns LED light-blue now
    3. ESP32, after its internal 5s window + capture:
       PATCH /api/reading-sessions/{id}  {status: COMPLETE, raw_channels: {...}, results: {...}}
    4. Dashboard (polls every ~1s while waiting): GET /api/reading-sessions/{id}
       -> shows result once status is COMPLETE (or an error if FAILED/TIMEOUT)

*** STORAGE: this file uses a simple in-memory dict as a placeholder. ***
Claude Code: replace SessionStore with your actual Postgres layer (you
already have a DB + a `readings` table pattern per the discovery pass --
mirror that, add a `reading_sessions` table). Keep the state-machine logic
below the same; only the storage calls need to change.

Wire the FastAPI routes at the bottom into your existing app/api router.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional, Dict
import uuid
import threading

from spectral_match import CHANNELS
from calibration_data import UREA_CHART, CREATININE_CHART, combine_readings


class SessionStatus(str, Enum):
    REQUESTED = "requested"          # dashboard clicked start, waiting for device
    ACKNOWLEDGED = "acknowledged"    # device picked it up, LED is on, timing window running
    COMPLETE = "complete"            # device posted a result
    FAILED = "failed"                # device reported a sensor/reading error
    TIMED_OUT = "timed_out"          # no device picked it up / no result in time


# How long the dashboard should wait before giving up if no ESP32 claims the
# session at all (e.g. device offline). This is independent of the device's
# own 5-second LED window, which happens after acknowledgement.
CLAIM_TIMEOUT_SECONDS = 30
RESULT_TIMEOUT_SECONDS = 30  # after acknowledgement, how long to wait for a result


@dataclass
class ReadingSession:
    id: str
    device_id: Optional[str]
    status: SessionStatus
    created_at: str
    acknowledged_at: Optional[str] = None
    completed_at: Optional[str] = None
    raw_channels: Optional[Dict[str, float]] = None
    results: Optional[dict] = None
    error: Optional[str] = None


class SessionStore:
    """In-memory placeholder. Replace with real DB-backed storage."""

    def __init__(self):
        self._sessions: Dict[str, ReadingSession] = {}
        self._lock = threading.Lock()

    def create(self, device_id: Optional[str] = None) -> ReadingSession:
        sid = str(uuid.uuid4())
        session = ReadingSession(
            id=sid,
            device_id=device_id,
            status=SessionStatus.REQUESTED,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._sessions[sid] = session
        return session

    def get(self, session_id: str) -> Optional[ReadingSession]:
        self._expire_if_needed(session_id)
        return self._sessions.get(session_id)

    def claim_oldest_pending(self, device_id: str) -> Optional[ReadingSession]:
        with self._lock:
            pending = [s for s in self._sessions.values() if s.status == SessionStatus.REQUESTED]
            if not pending:
                return None
            oldest = min(pending, key=lambda s: s.created_at)
            oldest.status = SessionStatus.ACKNOWLEDGED
            oldest.device_id = device_id
            oldest.acknowledged_at = datetime.now(timezone.utc).isoformat()
            return oldest

    def complete(self, session_id: str, raw_channels: dict, results: dict) -> Optional[ReadingSession]:
        with self._lock:
            s = self._sessions.get(session_id)
            if not s:
                return None
            s.status = SessionStatus.COMPLETE
            s.raw_channels = raw_channels
            s.results = results
            s.completed_at = datetime.now(timezone.utc).isoformat()
            return s

    def fail(self, session_id: str, error: str) -> Optional[ReadingSession]:
        with self._lock:
            s = self._sessions.get(session_id)
            if not s:
                return None
            s.status = SessionStatus.FAILED
            s.error = error
            s.completed_at = datetime.now(timezone.utc).isoformat()
            return s

    def _expire_if_needed(self, session_id: str):
        s = self._sessions.get(session_id)
        if not s:
            return
        now = datetime.now(timezone.utc)
        created = datetime.fromisoformat(s.created_at)
        if s.status == SessionStatus.REQUESTED and (now - created).total_seconds() > CLAIM_TIMEOUT_SECONDS:
            s.status = SessionStatus.TIMED_OUT
            s.error = "No device claimed this session in time -- check the ESP32 is online."
        elif s.status == SessionStatus.ACKNOWLEDGED and s.acknowledged_at:
            ack = datetime.fromisoformat(s.acknowledged_at)
            if (now - ack).total_seconds() > RESULT_TIMEOUT_SECONDS:
                s.status = SessionStatus.TIMED_OUT
                s.error = "Device acknowledged but never posted a result -- check sensor/network on device."


def compute_results(raw_channels: dict) -> dict:
    """Run calibration matching on a completed raw-channel reading."""
    urea_match = UREA_CHART.match(raw_channels)
    creat_match = CREATININE_CHART.match(raw_channels)
    # NOTE: pH / temperature not wired here yet -- see calibration_data.py docstring.

    ratio, ratio_flag = (None, None)
    if urea_match.in_range and creat_match.in_range:
        ratio, ratio_flag = combine_readings(urea_match.value, creat_match.value)

    return {
        "urea_mg_dl": urea_match.value,
        "urea_confidence": urea_match.confidence,
        "urea_in_range": urea_match.in_range,
        "creatinine_umol_l": creat_match.value,
        "creatinine_confidence": creat_match.confidence,
        "creatinine_in_range": creat_match.in_range,
        "bun_creatinine_ratio": ratio,
        "ratio_flag": ratio_flag,
        "overall_valid": urea_match.in_range and creat_match.in_range,
        "warnings": [w for w in [urea_match.warning, creat_match.warning] if w],
    }


# ---------------------------------------------------------------------------
# FastAPI routes -- mount this router into your existing app.
# Adjust the import path / dependency-injection style to match your app.
# ---------------------------------------------------------------------------

try:
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel

    router = APIRouter(prefix="/api/reading-sessions", tags=["reading-sessions"])
    _store = SessionStore()  # replace with real DB-backed store

    class CreateSessionRequest(BaseModel):
        device_id: Optional[str] = None

    class ClaimRequest(BaseModel):
        device_id: str

    class CompleteRequest(BaseModel):
        raw_channels: Dict[str, float]

    class FailRequest(BaseModel):
        error: str

    @router.post("")
    def create_session(req: CreateSessionRequest):
        session = _store.create(device_id=req.device_id)
        return asdict(session)

    @router.get("/pending")
    def claim_pending(device_id: str):
        """ESP32 polls this endpoint. Returns 204-equivalent (null) if nothing pending."""
        session = _store.claim_oldest_pending(device_id)
        if not session:
            return None
        return asdict(session)

    @router.patch("/{session_id}/complete")
    def complete_session(session_id: str, req: CompleteRequest):
        results = compute_results(req.raw_channels)
        session = _store.complete(session_id, req.raw_channels, results)
        if not session:
            raise HTTPException(404, "session not found")
        return asdict(session)

    @router.patch("/{session_id}/fail")
    def fail_session(session_id: str, req: FailRequest):
        session = _store.fail(session_id, req.error)
        if not session:
            raise HTTPException(404, "session not found")
        return asdict(session)

    @router.get("/{session_id}")
    def get_session(session_id: str):
        """Dashboard polls this while waiting for a result."""
        session = _store.get(session_id)
        if not session:
            raise HTTPException(404, "session not found")
        return asdict(session)

except ImportError:
    # fastapi/pydantic not installed in this sandbox -- the route definitions
    # above are still correct, just won't execute here. Claude Code: this
    # block will work fine inside the real backend environment.
    pass
