"""SQLite persistence for the orchestrator (brief §10). Self-contained + seeded
so the pipeline runs out of the box. Uses Python's stdlib sqlite3."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from .. import config

DB_PATH = config.PROJECT_ROOT / "novera_ai" / "orchestrator" / "orchestrator.db"


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY, name TEXT, phone TEXT, language TEXT DEFAULT 'en',
                diet TEXT, exercise TEXT, age INTEGER, created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS readings (
                id TEXT PRIMARY KEY, user_id TEXT, ph REAL, creatinine REAL, urea REAL,
                temperature REAL, confidence_score REAL, qa_passed INTEGER, captured_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS analysis_results (
                id TEXT PRIMARY KEY, reading_id TEXT, user_id TEXT,
                results_json TEXT, flagged_domains TEXT, threshold_crossed INTEGER,
                threshold_details TEXT, analyzed_at TEXT,
                FOREIGN KEY (reading_id) REFERENCES readings(id)
            );
            CREATE TABLE IF NOT EXISTS agent_outputs (
                id TEXT PRIMARY KEY, reading_id TEXT, user_id TEXT,
                insight_text TEXT, guidance_plan TEXT, voice_script TEXT,
                voice_audio_path TEXT, report_path TEXT, created_at TEXT,
                FOREIGN KEY (reading_id) REFERENCES readings(id)
            );
            CREATE TABLE IF NOT EXISTS appointments (
                id TEXT PRIMARY KEY, user_id TEXT, reading_id TEXT, slot_datetime TEXT,
                doctor_name TEXT, confirmation_number TEXT, booked_via TEXT DEFAULT 'whatsapp',
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS doctor_slots (
                id TEXT PRIMARY KEY, slot_datetime TEXT, doctor_name TEXT,
                is_available INTEGER DEFAULT 1
            );
            """
        )
        c.commit()
    _seed()


def _seed() -> None:
    with _conn() as c:
        if not c.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            phone = config.WHATSAPP_TO or "+96890000000"
            c.execute(
                "INSERT INTO users (id, name, phone, language, diet, exercise, age, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                ("demo-user", "Hussain", phone, "en",
                 "Coffee in the morning, moderate carbs, low water intake",
                 "2 hours of exercise daily", 28, now_iso()),
            )
        if not c.execute("SELECT 1 FROM doctor_slots LIMIT 1").fetchone():
            base = datetime.now().replace(minute=0, second=0, microsecond=0) + timedelta(days=1, hours=1)
            docs = ["Dr. Salim Al Habsi", "Dr. Aisha Al Balushi", "Dr. Omar Al Farsi"]
            for i in range(6):
                slot = base + timedelta(hours=i * 2)
                c.execute(
                    "INSERT INTO doctor_slots (id, slot_datetime, doctor_name, is_available) VALUES (?,?,?,1)",
                    (str(uuid.uuid4()), slot.isoformat(timespec="minutes"), docs[i % len(docs)]),
                )
        c.commit()


# ---- users ----
def get_user(user_id: str) -> Optional[dict[str, Any]]:
    with _conn() as c:
        row = c.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def get_user_by_phone(phone: str) -> Optional[dict[str, Any]]:
    with _conn() as c:
        row = c.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
    return dict(row) if row else None


def update_user_language(user_id: str, lang: str) -> None:
    with _conn() as c:
        c.execute("UPDATE users SET language = ? WHERE id = ?", (lang, user_id))
        c.commit()


# ---- readings / analysis / outputs ----
def save_reading(user_id: str, reading: dict, confidence: float, qa_passed: bool) -> str:
    rid = str(uuid.uuid4())
    with _conn() as c:
        c.execute(
            "INSERT INTO readings (id, user_id, ph, creatinine, urea, temperature, "
            "confidence_score, qa_passed, captured_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (rid, user_id, reading.get("ph"), reading.get("creatinine"), reading.get("urea"),
             reading.get("temperature"), confidence, 1 if qa_passed else 0, now_iso()),
        )
        c.commit()
    return rid


def save_analysis(reading_id, user_id, results, flagged, crossed, details) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO analysis_results (id, reading_id, user_id, results_json, flagged_domains, "
            "threshold_crossed, threshold_details, analyzed_at) VALUES (?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), reading_id, user_id, json.dumps(results, ensure_ascii=False),
             json.dumps(flagged, ensure_ascii=False), 1 if crossed else 0,
             json.dumps(details, ensure_ascii=False), now_iso()),
        )
        c.commit()


def save_outputs(reading_id, user_id, insight, guidance, voice_script, voice_audio_path, report_path) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO agent_outputs (id, reading_id, user_id, insight_text, guidance_plan, "
            "voice_script, voice_audio_path, report_path, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), reading_id, user_id, insight, guidance, voice_script,
             voice_audio_path, report_path, now_iso()),
        )
        c.commit()


def load_latest_state(user_id: str) -> dict[str, Any]:
    """Rebuild a partial state for WhatsApp re-entry (brief §11)."""
    with _conn() as c:
        r = c.execute(
            "SELECT * FROM readings WHERE user_id = ? ORDER BY captured_at DESC LIMIT 1", (user_id,)
        ).fetchone()
        if not r:
            return {}
        a = c.execute(
            "SELECT * FROM analysis_results WHERE reading_id = ? ORDER BY analyzed_at DESC LIMIT 1", (r["id"],)
        ).fetchone()
        o = c.execute(
            "SELECT * FROM agent_outputs WHERE reading_id = ? ORDER BY created_at DESC LIMIT 1", (r["id"],)
        ).fetchone()
    u = get_user(user_id) or {}
    return {
        "user_id": user_id,
        "reading_id": r["id"],
        "raw_reading": {k: r[k] for k in ("ph", "creatinine", "urea", "temperature")},
        "analysis_results": json.loads(a["results_json"]) if a else {},
        "flagged_domains": json.loads(a["flagged_domains"]) if a else [],
        "threshold_crossed": bool(a["threshold_crossed"]) if a else False,
        "insight_text": o["insight_text"] if o else "",
        "guidance_plan": o["guidance_plan"] if o else "",
        "report_path": o["report_path"] if o else "",
        "user_context": {
            "name": u.get("name", ""), "phone": u.get("phone", ""), "language": u.get("language", "en"),
            "diet": u.get("diet", ""), "exercise": u.get("exercise", ""), "age": u.get("age"),
        },
    }


def list_outputs(user_id: str, limit: int = 20) -> list[dict[str, Any]]:
    with _conn() as c:
        rows = c.execute(
            "SELECT o.*, r.captured_at AS reading_at FROM agent_outputs o "
            "JOIN readings r ON r.id = o.reading_id WHERE o.user_id = ? "
            "ORDER BY o.created_at DESC LIMIT ?", (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


# ---- appointments / slots ----
def get_open_slots(limit: int = 10) -> list[dict[str, Any]]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM doctor_slots WHERE is_available = 1 ORDER BY slot_datetime ASC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def book_nearest_slot(user_id: str, reading_id: Optional[str]) -> Optional[dict[str, Any]]:
    with _conn() as c:
        slot = c.execute(
            "SELECT * FROM doctor_slots WHERE is_available = 1 ORDER BY slot_datetime ASC LIMIT 1"
        ).fetchone()
        if not slot:
            return None
        c.execute("UPDATE doctor_slots SET is_available = 0 WHERE id = ?", (slot["id"],))
        conf = "NOV-" + str(uuid.uuid4())[:8].upper()
        appt_id = str(uuid.uuid4())
        c.execute(
            "INSERT INTO appointments (id, user_id, reading_id, slot_datetime, doctor_name, "
            "confirmation_number, booked_via, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (appt_id, user_id, reading_id, slot["slot_datetime"], slot["doctor_name"], conf, "whatsapp", now_iso()),
        )
        c.commit()
    return {
        "slot_datetime": slot["slot_datetime"],
        "doctor_name": slot["doctor_name"],
        "confirmation_number": conf,
    }
