from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional, TypedDict

import requests
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field, ValidationError

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

ORGANS = ("KIDNEY", "STOMACH", "ORAL")
BIOMARKERS = ("ph", "urea_mg_dl", "creatinine_umol_l", "temperature_c")


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


DATABASE_PATH = resolve_path(os.getenv("DATABASE_PATH", "novera.db"))
CONFIRMED_CASE_QUERY_LIMIT = max(
    3, int(os.getenv("CONFIRMED_CASE_QUERY_LIMIT", "25"))
)
OPENROUTER_TIMEOUT_SECONDS = max(
    15, int(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "60"))
)
OPENROUTER_MODEL_SETTING = os.getenv("OPENROUTER_MODEL", "auto").strip() or "auto"

DEFAULT_REFERENCE_RANGES: dict[str, dict[str, tuple[float, float, float]]] = {
    "KIDNEY": {
        "ph": (6.2, 7.6, 1.0),
        "urea_mg_dl": (20.0, 30.0, 1.2),
        "creatinine_umol_l": (18.0, 25.0, 1.3),
        "temperature_c": (35.0, 37.0, 0.8),
    },
    "STOMACH": {
        "ph": (6.5, 7.6, 1.2),
        "urea_mg_dl": (20.0, 45.0, 1.0),
        "creatinine_umol_l": (18.0, 40.0, 0.9),
        "temperature_c": (35.0, 37.0, 0.8),
    },
    "ORAL": {
        "ph": (6.3, 7.6, 1.3),
        "urea_mg_dl": (20.0, 45.0, 0.9),
        "creatinine_umol_l": (18.0, 40.0, 0.8),
        "temperature_c": (35.0, 37.0, 0.8),
    },
}


class FinalDecision(BaseModel):
    """The only output accepted from the OpenRouter model."""

    prediction: Literal["KIDNEY", "STOMACH", "ORAL"]
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=15, max_length=600)


class GraphState(TypedDict, total=False):
    reading: Optional[dict[str, Any]]
    validation_errors: list[str]
    specialist_results: list[dict[str, Any]]
    selected_model: Optional[str]
    llm_result: Optional[dict[str, Any]]
    final_decision: Optional[dict[str, Any]]
    result: dict[str, Any]


@dataclass(frozen=True)
class RangeSpec:
    min_value: float
    max_value: float
    weight: float


class OpenRouterDecisionError(RuntimeError):
    """Raised when OpenRouter does not produce a valid single-organ decision."""


class Database:
    def __init__(self, path: Path):
        self.path = path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def initialize(self) -> None:
        """Create or safely migrate the database to the clean schema."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            self._create_reference_ranges_table(connection)
            self._create_clean_tables_if_missing(connection)
            connection.commit()

        self._migrate_old_schema_if_needed()
        self._seed_reference_ranges()

    @staticmethod
    def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
        row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (name,),
        ).fetchone()
        return row is not None

    @staticmethod
    def _table_columns(connection: sqlite3.Connection, name: str) -> set[str]:
        if not Database._table_exists(connection, name):
            return set()
        return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({name})")}

    @staticmethod
    def _create_reference_ranges_table(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS reference_ranges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organ TEXT NOT NULL CHECK (organ IN ('KIDNEY', 'STOMACH', 'ORAL')),
                biomarker TEXT NOT NULL CHECK (
                    biomarker IN ('ph', 'urea_mg_dl', 'creatinine_umol_l', 'temperature_c')
                ),
                min_value REAL NOT NULL,
                max_value REAL NOT NULL,
                weight REAL NOT NULL DEFAULT 1.0,
                UNIQUE (organ, biomarker),
                CHECK (max_value > min_value)
            )
            """
        )

    @staticmethod
    def _create_clean_tables_if_missing(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL UNIQUE,
                ph REAL NOT NULL,
                urea_mg_dl REAL NOT NULL,
                creatinine_umol_l REAL NOT NULL,
                temperature_c REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'NEW' CHECK (
                    status IN ('NEW', 'PROCESSING', 'COMPLETED', 'RETEST_REQUIRED', 'ERROR')
                ),
                ai_prediction TEXT CHECK (
                    ai_prediction IS NULL OR ai_prediction IN ('KIDNEY', 'STOMACH', 'ORAL')
                ),
                ai_confidence REAL,
                ai_reason TEXT,
                human_confirmation TEXT CHECK (
                    human_confirmation IS NULL OR
                    human_confirmation IN ('KIDNEY', 'STOMACH', 'ORAL')
                )
            );

            CREATE TABLE IF NOT EXISTS confirmed_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reading_id INTEGER NOT NULL UNIQUE,
                organ TEXT NOT NULL CHECK (organ IN ('KIDNEY', 'STOMACH', 'ORAL')),
                notes TEXT,
                confirmed_by TEXT,
                FOREIGN KEY (reading_id) REFERENCES readings(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS decision_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reading_id INTEGER NOT NULL,
                selected_model TEXT NOT NULL,
                llm_used INTEGER NOT NULL CHECK (llm_used IN (0, 1)),
                specialist_results_json TEXT NOT NULL,
                llm_result_json TEXT NOT NULL,
                final_prediction TEXT NOT NULL CHECK (
                    final_prediction IN ('KIDNEY', 'STOMACH', 'ORAL')
                ),
                final_confidence REAL NOT NULL,
                final_reason TEXT NOT NULL,
                FOREIGN KEY (reading_id) REFERENCES readings(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_readings_status_id
                ON readings (status, id DESC);
            CREATE INDEX IF NOT EXISTS idx_confirmed_cases_organ_id
                ON confirmed_cases (organ, id DESC);
            CREATE INDEX IF NOT EXISTS idx_decision_audit_reading_id
                ON decision_audit (reading_id, id DESC);
            """
        )
        Database._create_views(connection)

    @staticmethod
    def _create_views(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            DROP VIEW IF EXISTS case_results;
            CREATE VIEW case_results AS
            SELECT
                case_id,
                ph,
                urea_mg_dl,
                creatinine_umol_l,
                temperature_c,
                status,
                ai_prediction,
                ai_confidence,
                ai_reason,
                human_confirmation
            FROM readings
            ORDER BY id;

            DROP VIEW IF EXISTS confirmed_memory;
            CREATE VIEW confirmed_memory AS
            SELECT
                r.case_id,
                c.organ,
                r.ph,
                r.urea_mg_dl,
                r.creatinine_umol_l,
                r.temperature_c,
                c.notes,
                c.confirmed_by
            FROM confirmed_cases AS c
            JOIN readings AS r ON r.id = c.reading_id
            ORDER BY r.id;
            """
        )

    def _migrate_old_schema_if_needed(self) -> None:
        """
        Remove unwanted legacy columns while preserving existing readings,
        confirmations, IDs, and audit rows.
        """
        with self.connect() as connection:
            reading_columns = self._table_columns(connection, "readings")
            confirmed_columns = self._table_columns(connection, "confirmed_cases")
            audit_columns = self._table_columns(connection, "decision_audit")

        legacy_reading_columns = {"prediction_correct", "created_at", "processed_at"}
        legacy_confirmed_columns = {"confirmed_at"}
        legacy_audit_columns = {"created_at"}

        needs_migration = bool(
            reading_columns & legacy_reading_columns
            or confirmed_columns & legacy_confirmed_columns
            or audit_columns & legacy_audit_columns
        )
        if not needs_migration:
            return

        connection = sqlite3.connect(self.path, timeout=20)
        try:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute("BEGIN IMMEDIATE")
            connection.executescript(
                """
                DROP VIEW IF EXISTS case_results;
                DROP VIEW IF EXISTS confirmed_memory;
                DROP INDEX IF EXISTS idx_readings_status_id;
                DROP INDEX IF EXISTS idx_confirmed_cases_organ_id;
                DROP INDEX IF EXISTS idx_decision_audit_reading_id;

                ALTER TABLE confirmed_cases RENAME TO confirmed_cases_legacy;
                ALTER TABLE decision_audit RENAME TO decision_audit_legacy;
                ALTER TABLE readings RENAME TO readings_legacy;

                CREATE TABLE readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL UNIQUE,
                    ph REAL NOT NULL,
                    urea_mg_dl REAL NOT NULL,
                    creatinine_umol_l REAL NOT NULL,
                    temperature_c REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'NEW' CHECK (
                        status IN ('NEW', 'PROCESSING', 'COMPLETED', 'RETEST_REQUIRED', 'ERROR')
                    ),
                    ai_prediction TEXT CHECK (
                        ai_prediction IS NULL OR ai_prediction IN ('KIDNEY', 'STOMACH', 'ORAL')
                    ),
                    ai_confidence REAL,
                    ai_reason TEXT,
                    human_confirmation TEXT CHECK (
                        human_confirmation IS NULL OR
                        human_confirmation IN ('KIDNEY', 'STOMACH', 'ORAL')
                    )
                );

                INSERT INTO readings (
                    id, case_id, ph, urea_mg_dl, creatinine_umol_l,
                    temperature_c, status, ai_prediction, ai_confidence,
                    ai_reason, human_confirmation
                )
                SELECT
                    id, case_id, ph, urea_mg_dl, creatinine_umol_l,
                    temperature_c, status,
                    CASE
                        WHEN ai_prediction IN ('KIDNEY', 'STOMACH', 'ORAL')
                        THEN ai_prediction ELSE NULL
                    END,
                    ai_confidence, ai_reason, human_confirmation
                FROM readings_legacy;

                CREATE TABLE confirmed_cases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reading_id INTEGER NOT NULL UNIQUE,
                    organ TEXT NOT NULL CHECK (organ IN ('KIDNEY', 'STOMACH', 'ORAL')),
                    notes TEXT,
                    confirmed_by TEXT,
                    FOREIGN KEY (reading_id) REFERENCES readings(id) ON DELETE CASCADE
                );

                INSERT INTO confirmed_cases (id, reading_id, organ, notes, confirmed_by)
                SELECT id, reading_id, organ, notes, confirmed_by
                FROM confirmed_cases_legacy;

                CREATE TABLE decision_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reading_id INTEGER NOT NULL,
                    selected_model TEXT NOT NULL,
                    llm_used INTEGER NOT NULL CHECK (llm_used IN (0, 1)),
                    specialist_results_json TEXT NOT NULL,
                    llm_result_json TEXT NOT NULL,
                    final_prediction TEXT NOT NULL CHECK (
                        final_prediction IN ('KIDNEY', 'STOMACH', 'ORAL')
                    ),
                    final_confidence REAL NOT NULL,
                    final_reason TEXT NOT NULL,
                    FOREIGN KEY (reading_id) REFERENCES readings(id) ON DELETE CASCADE
                );
                """
            )

            legacy_audit_count = connection.execute(
                "SELECT COUNT(*) FROM decision_audit_legacy"
            ).fetchone()[0]
            if legacy_audit_count:
                connection.execute(
                    """
                    INSERT INTO decision_audit (
                        id, reading_id, selected_model, llm_used,
                        specialist_results_json, llm_result_json,
                        final_prediction, final_confidence, final_reason
                    )
                    SELECT
                        id,
                        reading_id,
                        COALESCE(selected_model, 'unknown'),
                        llm_used,
                        specialist_results_json,
                        COALESCE(llm_result_json, '{}'),
                        CASE
                            WHEN final_prediction IN ('KIDNEY', 'STOMACH', 'ORAL')
                            THEN final_prediction
                            ELSE COALESCE(
                                (SELECT ai_prediction FROM readings WHERE id = reading_id),
                                'KIDNEY'
                            )
                        END,
                        COALESCE(final_confidence, 0.0),
                        COALESCE(final_reason, '')
                    FROM decision_audit_legacy
                    """
                )

            connection.executescript(
                """
                DROP TABLE confirmed_cases_legacy;
                DROP TABLE decision_audit_legacy;
                DROP TABLE readings_legacy;

                CREATE INDEX idx_readings_status_id
                    ON readings (status, id DESC);
                CREATE INDEX idx_confirmed_cases_organ_id
                    ON confirmed_cases (organ, id DESC);
                CREATE INDEX idx_decision_audit_reading_id
                    ON decision_audit (reading_id, id DESC);
                """
            )
            self._create_views(connection)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _seed_reference_ranges(self) -> None:
        with self.connect() as connection:
            for organ, biomarkers in DEFAULT_REFERENCE_RANGES.items():
                for biomarker, (minimum, maximum, weight) in biomarkers.items():
                    connection.execute(
                        """
                        INSERT INTO reference_ranges (
                            organ, biomarker, min_value, max_value, weight
                        ) VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(organ, biomarker) DO UPDATE SET
                            min_value = excluded.min_value,
                            max_value = excluded.max_value,
                            weight = excluded.weight
                        """,
                        (organ, biomarker, minimum, maximum, weight),
                    )
            connection.commit()

    def load_reference_ranges(self) -> dict[str, dict[str, RangeSpec]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT organ, biomarker, min_value, max_value, weight
                FROM reference_ranges
                ORDER BY organ, biomarker
                """
            ).fetchall()

        output: dict[str, dict[str, RangeSpec]] = {organ: {} for organ in ORGANS}
        for row in rows:
            output[str(row["organ"])][str(row["biomarker"])] = RangeSpec(
                min_value=float(row["min_value"]),
                max_value=float(row["max_value"]),
                weight=float(row["weight"]),
            )

        for organ in ORGANS:
            missing = set(BIOMARKERS) - set(output[organ])
            if missing:
                raise RuntimeError(
                    f"Reference ranges are incomplete for {organ}: {sorted(missing)}"
                )
        return output

    def add_reading(
        self,
        ph: float,
        urea_mg_dl: float,
        creatinine_umol_l: float,
        temperature_c: float,
    ) -> str:
        """Insert one NEW reading and generate the next N-number case ID."""
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT MAX(CAST(SUBSTR(case_id, 2) AS INTEGER)) AS max_number
                FROM readings
                WHERE case_id GLOB 'N[0-9]*'
                """
            ).fetchone()
            next_number = int(row["max_number"] or 0) + 1
            case_id = f"N{next_number:03d}"
            connection.execute(
                """
                INSERT INTO readings (
                    case_id, ph, urea_mg_dl, creatinine_umol_l,
                    temperature_c, status
                ) VALUES (?, ?, ?, ?, ?, 'NEW')
                """,
                (
                    case_id,
                    ph,
                    urea_mg_dl,
                    creatinine_umol_l,
                    temperature_c,
                ),
            )
            connection.commit()
        return case_id

    def fetch_latest_new_reading(self) -> Optional[dict[str, Any]]:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, case_id, ph, urea_mg_dl, creatinine_umol_l,
                       temperature_c, status
                FROM readings
                WHERE status = 'NEW'
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        return dict(row) if row else None

    def claim_reading(self, reading_id: int) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE readings
                SET status = 'PROCESSING'
                WHERE id = ? AND status = 'NEW'
                """,
                (reading_id,),
            )
            connection.commit()
            return cursor.rowcount == 1

    def release_reading(self, reading_id: int) -> None:
        """Return a failed OpenRouter case to NEW without saving a fake prediction."""
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE readings
                SET status = 'NEW', ai_prediction = NULL,
                    ai_confidence = NULL, ai_reason = NULL
                WHERE id = ?
                """,
                (reading_id,),
            )
            connection.commit()

    def fetch_confirmed_cases(self, organ: str, limit: int) -> list[dict[str, Any]]:
        """Query only a limited, organ-specific subset from confirmed memory."""
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    r.id,
                    r.case_id,
                    r.ph,
                    r.urea_mg_dl,
                    r.creatinine_umol_l,
                    r.temperature_c
                FROM confirmed_cases AS c
                JOIN readings AS r ON r.id = c.reading_id
                WHERE c.organ = ?
                ORDER BY c.id DESC
                LIMIT ?
                """,
                (organ, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def persist_decision(
        self,
        reading: dict[str, Any],
        decision: dict[str, Any],
        specialist_results: list[dict[str, Any]],
        selected_model: str,
        llm_result: dict[str, Any],
    ) -> None:
        prediction = str(decision["prediction"]).upper()
        if prediction not in ORGANS:
            raise ValueError("Only a single organ prediction can be saved.")

        with self.connect() as connection:
            connection.execute(
                """
                UPDATE readings
                SET status = 'COMPLETED', ai_prediction = ?,
                    ai_confidence = ?, ai_reason = ?
                WHERE id = ?
                """,
                (
                    prediction,
                    float(decision["confidence"]),
                    str(decision["reason"]),
                    reading["id"],
                ),
            )
            connection.execute(
                """
                INSERT INTO decision_audit (
                    reading_id,
                    selected_model,
                    llm_used,
                    specialist_results_json,
                    llm_result_json,
                    final_prediction,
                    final_confidence,
                    final_reason
                ) VALUES (?, ?, 1, ?, ?, ?, ?, ?)
                """,
                (
                    reading["id"],
                    selected_model,
                    json.dumps(specialist_results, ensure_ascii=False),
                    json.dumps(llm_result, ensure_ascii=False),
                    prediction,
                    float(decision["confidence"]),
                    str(decision["reason"]),
                ),
            )
            connection.commit()

    def confirm_case(
        self,
        case_id: str,
        organ: str,
        confirmed_by: Optional[str],
        notes: Optional[str],
    ) -> dict[str, Any]:
        organ = organ.upper()
        if organ not in ORGANS:
            raise ValueError(f"organ must be one of: {', '.join(ORGANS)}")

        with self.connect() as connection:
            reading = connection.execute(
                """
                SELECT id, ai_prediction
                FROM readings
                WHERE case_id = ?
                LIMIT 1
                """,
                (case_id,),
            ).fetchone()
            if not reading:
                raise ValueError(f"Case not found: {case_id}")

            connection.execute(
                """
                INSERT INTO confirmed_cases (reading_id, organ, notes, confirmed_by)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(reading_id) DO UPDATE SET
                    organ = excluded.organ,
                    notes = excluded.notes,
                    confirmed_by = excluded.confirmed_by
                """,
                (reading["id"], organ, notes, confirmed_by),
            )
            connection.execute(
                """
                UPDATE readings
                SET human_confirmation = ?
                WHERE id = ?
                """,
                (organ, reading["id"]),
            )
            connection.commit()

        return {
            "case_id": case_id,
            "ai_prediction": reading["ai_prediction"],
            "human_confirmation": organ,
            "matches_ai": (
                None
                if reading["ai_prediction"] not in ORGANS
                else bool(reading["ai_prediction"] == organ)
            ),
        }

    def get_case(self, case_id: str) -> Optional[dict[str, Any]]:
        """Return only the clean fields the user asked to see."""
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    case_id,
                    ph,
                    urea_mg_dl,
                    creatinine_umol_l,
                    temperature_c,
                    status,
                    ai_prediction,
                    ai_confidence,
                    ai_reason,
                    human_confirmation
                FROM readings
                WHERE case_id = ?
                LIMIT 1
                """,
                (case_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_cases(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    case_id,
                    status,
                    ai_prediction,
                    ai_confidence,
                    human_confirmation
                FROM readings
                ORDER BY id DESC
                LIMIT ?
                """,
                (max(1, limit),),
            ).fetchall()
        return [dict(row) for row in rows]


# -----------------------------------------------------------------------------
# Deterministic specialist tools
# -----------------------------------------------------------------------------

class ScoringEngine:
    def __init__(
        self,
        database: Database,
        ranges: dict[str, dict[str, RangeSpec]],
        confirmed_limit: int,
    ):
        self.database = database
        self.ranges = ranges
        self.confirmed_limit = confirmed_limit

    @staticmethod
    def get_ml_score(organ: str, values: dict[str, float]) -> None:
        """Reserved interface for a future trained model. No ML is used now."""
        _ = organ, values
        return None

    @staticmethod
    def _value_fit(value: float, spec: RangeSpec) -> tuple[float, str, float]:
        width = max(spec.max_value - spec.min_value, 1e-9)
        if spec.min_value <= value <= spec.max_value:
            midpoint = (spec.min_value + spec.max_value) / 2.0
            half_width = width / 2.0
            centrality = 1.0 - min(abs(value - midpoint) / max(half_width, 1e-9), 1.0)
            score = 0.85 + 0.15 * centrality
            return score, "inside", 0.0

        distance = (
            spec.min_value - value if value < spec.min_value else value - spec.max_value
        )
        normalized_deviation = distance / width
        score = max(0.0, 0.85 - normalized_deviation)
        flag = "borderline" if normalized_deviation <= 0.15 else "outside"
        return score, flag, normalized_deviation

    def _range_score(
        self,
        organ: str,
        values: dict[str, float],
    ) -> tuple[float, dict[str, Any]]:
        weighted_total = 0.0
        total_weight = 0.0
        details: dict[str, Any] = {}

        for biomarker in BIOMARKERS:
            spec = self.ranges[organ][biomarker]
            score, flag, deviation = self._value_fit(values[biomarker], spec)
            weighted_total += score * spec.weight
            total_weight += spec.weight
            details[biomarker] = {
                "value": round(values[biomarker], 4),
                "min": spec.min_value,
                "max": spec.max_value,
                "fit": round(score, 4),
                "flag": flag,
                "normalized_deviation": round(deviation, 4),
            }

        return weighted_total / max(total_weight, 1e-9), details

    def _similarity_score(
        self,
        organ: str,
        values: dict[str, float],
    ) -> tuple[float, int, list[dict[str, Any]]]:
        candidates = self.database.fetch_confirmed_cases(organ, self.confirmed_limit)
        similarities: list[dict[str, Any]] = []

        for case in candidates:
            squared_differences: list[float] = []
            for biomarker in BIOMARKERS:
                spec = self.ranges[organ][biomarker]
                width = max(spec.max_value - spec.min_value, 1e-9)
                normalized_difference = (
                    values[biomarker] - float(case[biomarker])
                ) / width
                squared_differences.append(normalized_difference**2)

            distance = math.sqrt(
                sum(squared_differences) / len(squared_differences)
            )
            similarity = 1.0 / (1.0 + distance)
            similarities.append(
                {
                    "case_id": case["case_id"],
                    "similarity": round(similarity, 4),
                    "distance": round(distance, 4),
                }
            )

        similarities.sort(key=lambda item: item["similarity"], reverse=True)
        closest = similarities[:3]
        score = (
            sum(item["similarity"] for item in closest) / len(closest)
            if closest
            else 0.0
        )
        return score, len(candidates), closest

    def evaluate(self, organ: str, values: dict[str, float]) -> dict[str, Any]:
        range_score, biomarker_details = self._range_score(organ, values)
        similarity_score, candidate_count, closest_cases = self._similarity_score(
            organ, values
        )
        ml_score = self.get_ml_score(organ, values)

        combined_score = (
            0.55 * range_score + 0.45 * similarity_score
            if candidate_count > 0
            else range_score
        )

        if combined_score >= 0.80:
            flag = "high"
        elif combined_score >= 0.60:
            flag = "medium"
        else:
            flag = "low"

        return {
            "organ": organ,
            "range_score": round(range_score, 4),
            "similarity_score": round(similarity_score, 4),
            "combined_score": round(combined_score, 4),
            "matched_cases": len(closest_cases),
            "candidate_cases_queried": candidate_count,
            "flag": flag,
            "biomarkers": biomarker_details,
            "closest_confirmed_cases": closest_cases,
            "ml_score": ml_score,
        }


# -----------------------------------------------------------------------------
# OpenRouter: exactly one LLM call per processed case
# -----------------------------------------------------------------------------

class OpenRouterDecisionMaker:
    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        self.model_setting = OPENROUTER_MODEL_SETTING

    def _models_catalogue(self) -> list[dict[str, Any]]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        response = requests.get(
            "https://openrouter.ai/api/v1/models",
            params={
                "supported_parameters": "tools",
                "sort": "throughput-high-to-low",
            },
            headers=headers,
            timeout=20,
        )
        response.raise_for_status()
        return list(response.json().get("data", []))

    @staticmethod
    def _is_free_tool_model(model: dict[str, Any]) -> bool:
        supported = set(model.get("supported_parameters") or [])
        pricing = model.get("pricing") or {}
        model_id = str(model.get("id", ""))
        try:
            prompt_price = float(pricing.get("prompt", 1))
            completion_price = float(pricing.get("completion", 1))
        except (TypeError, ValueError):
            return False

        return bool(
            model_id
            and "tools" in supported
            and "tool_choice" in supported
            and prompt_price == 0.0
            and completion_price == 0.0
        )

    def resolve_model(self) -> str:
        """
        Confirm that a current free tool-calling model exists before using the
        OpenRouter free router. A user-specified model is validated against the
        current catalogue instead of being blindly trusted.
        """
        try:
            catalogue = self._models_catalogue()
        except Exception as exc:
            raise OpenRouterDecisionError(
                "OpenRouter model availability could not be checked."
            ) from exc

        free_tool_models = [m for m in catalogue if self._is_free_tool_model(m)]
        if not free_tool_models:
            raise OpenRouterDecisionError(
                "No currently available free tool-calling model was found."
            )

        if self.model_setting.lower() == "auto":
            # Avoid a stale hardcoded model slug. OpenRouter selects a currently
            # available free model that supports the requested tool schema.
            return "openrouter/free"

        configured = next(
            (m for m in catalogue if str(m.get("id")) == self.model_setting),
            None,
        )
        if configured is None or not self._is_free_tool_model(configured):
            raise OpenRouterDecisionError(
                "The configured OpenRouter model is not currently available as a free tool-calling model."
            )
        return self.model_setting

    @staticmethod
    def _extract_tool_arguments(response: Any) -> dict[str, Any]:
        tool_calls = getattr(response, "tool_calls", None) or []
        for call in tool_calls:
            name = str(call.get("name", ""))
            if name == "FinalDecision":
                args = call.get("args", {})
                if isinstance(args, dict):
                    return args

        # Compatibility path for SDK/provider responses that keep raw calls in
        # additional_kwargs rather than normalizing them.
        additional = getattr(response, "additional_kwargs", {}) or {}
        raw_calls = additional.get("tool_calls") or []
        for call in raw_calls:
            function = call.get("function") or {}
            if function.get("name") != "FinalDecision":
                continue
            raw_args = function.get("arguments", "{}")
            if isinstance(raw_args, dict):
                return raw_args
            try:
                parsed = json.loads(raw_args)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(parsed, dict):
                return parsed

        raise OpenRouterDecisionError(
            "OpenRouter did not return the required decision structure."
        )

    def decide(
        self,
        reading: dict[str, Any],
        specialist_results: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], str, dict[str, Any]]:
        if not self.api_key or not self.api_key.startswith("sk-or-"):
            raise OpenRouterDecisionError(
                "A valid OPENROUTER_API_KEY is not configured in .env."
            )

        model = self.resolve_model()

        compact_results = [
            {
                "organ": item["organ"],
                "range_score": item["range_score"],
                "similarity_score": item["similarity_score"],
                "combined_score": item["combined_score"],
                "matched_cases": item["matched_cases"],
                "flag": item["flag"],
                "closest_confirmed_cases": item["closest_confirmed_cases"],
            }
            for item in specialist_results
        ]

        llm = ChatOpenAI(
            model=model,
            api_key=self.api_key,
            base_url="https://openrouter.ai/api/v1",
            temperature=0,
            timeout=OPENROUTER_TIMEOUT_SECONDS,
            max_retries=0,
            default_headers={
                "HTTP-Referer": "http://localhost",
                "X-Title": "NOVERA Screening Core",
            },
        )

        # Forced tool output guarantees one of only three organs. This is the
        # single and only LLM invocation for the case.
        decision_llm = llm.bind_tools(
            [FinalDecision],
            tool_choice="FinalDecision",
            parallel_tool_calls=False,
        )

        ranked = sorted(
            compact_results,
            key=lambda item: item["combined_score"],
            reverse=True,
        )
        deterministic_leader = ranked[0]["organ"]

        messages = [
            SystemMessage(
                content=(
                    "You are the NOVERA final screening decision component. "
                    "This is experimental screening support, not a confirmed diagnosis. "
                    "The Kidney, Stomach, and Oral specialist results were calculated "
                    "before this call using project reference ranges and limited "
                    "human-confirmed SQL memory. Make exactly one final prediction: "
                    "KIDNEY, STOMACH, or ORAL. Never output MULTIPLE, NO_CLEAR_PATTERN, "
                    "or any other label. Use only the supplied evidence. The reason must "
                    "be a concise final explanation that mentions the important range "
                    "score, similarity score, and confirmed-case support. Do not invent "
                    "medical thresholds, diagnoses, or historical cases."
                )
            ),
            HumanMessage(
                content=json.dumps(
                    {
                        "case_id": reading["case_id"],
                        "values": {key: reading[key] for key in BIOMARKERS},
                        "deterministic_leader": deterministic_leader,
                        "specialist_results": compact_results,
                    },
                    ensure_ascii=False,
                )
            ),
        ]

        try:
            response = decision_llm.invoke(messages)  # exactly one LLM call
            arguments = self._extract_tool_arguments(response)
            validated = FinalDecision.model_validate(arguments)
        except (OpenRouterDecisionError, ValidationError) as exc:
            raise OpenRouterDecisionError(
                "OpenRouter did not return a valid single-organ decision."
            ) from exc
        except Exception as exc:
            raise OpenRouterDecisionError(
                "OpenRouter could not complete the decision."
            ) from exc

        decision = validated.model_dump()
        decision["prediction"] = str(decision["prediction"]).upper()
        decision["confidence"] = round(float(decision["confidence"]), 4)
        decision["reason"] = str(decision["reason"]).strip()

        if decision["prediction"] not in ORGANS:
            raise OpenRouterDecisionError(
                "OpenRouter returned an unsupported prediction."
            )
        if not decision["reason"]:
            raise OpenRouterDecisionError(
                "OpenRouter returned no explanation."
            )

        response_metadata = getattr(response, "response_metadata", {}) or {}
        actual_model = str(
            response_metadata.get("model_name")
            or response_metadata.get("model")
            or model
        )
        raw_result = {
            "prediction": decision["prediction"],
            "confidence": decision["confidence"],
            "reason": decision["reason"],
        }
        return decision, actual_model, raw_result


# -----------------------------------------------------------------------------
# Validation and LangGraph pipeline
# -----------------------------------------------------------------------------

def validate_reading(reading: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    checks = {
        "ph": (0.0, 14.0),
        "urea_mg_dl": (0.0, 500.0),
        "creatinine_umol_l": (0.0, 2000.0),
        "temperature_c": (20.0, 45.0),
    }

    for field, (minimum, maximum) in checks.items():
        try:
            value = float(reading[field])
        except (KeyError, TypeError, ValueError):
            errors.append(f"{field} is missing or not numeric")
            continue
        if not minimum <= value <= maximum:
            errors.append(
                f"{field} is outside the plausible input range {minimum}-{maximum}"
            )
    return errors


class NoveraService:
    def __init__(self, database_path: Path = DATABASE_PATH):
        self.database = Database(database_path)
        self.database.initialize()
        self.reference_ranges = self.database.load_reference_ranges()
        self.scoring = ScoringEngine(
            self.database,
            self.reference_ranges,
            CONFIRMED_CASE_QUERY_LIMIT,
        )
        self.decision_maker = OpenRouterDecisionMaker()
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(GraphState)
        graph.add_node("fetch_latest_case", self._fetch_latest_case)
        graph.add_node("validate_case", self._validate_case)
        graph.add_node("run_specialist_tools", self._run_specialist_tools)
        graph.add_node("make_llm_decision", self._make_llm_decision)
        graph.add_node("save_decision", self._save_decision)

        graph.add_edge(START, "fetch_latest_case")
        graph.add_conditional_edges(
            "fetch_latest_case",
            self._route_after_fetch,
            {"case": "validate_case", "none": END},
        )
        graph.add_conditional_edges(
            "validate_case",
            self._route_after_validation,
            {"valid": "run_specialist_tools", "invalid": "save_decision"},
        )
        graph.add_edge("run_specialist_tools", "make_llm_decision")
        graph.add_conditional_edges(
            "make_llm_decision",
            self._route_after_llm,
            {"success": "save_decision", "failed": END},
        )
        graph.add_edge("save_decision", END)
        return graph.compile()

    def _fetch_latest_case(self, state: GraphState) -> GraphState:
        _ = state
        reading = self.database.fetch_latest_new_reading()
        if reading is None:
            return {"reading": None, "result": {"status": "NO_NEW_CASE"}}
        if not self.database.claim_reading(int(reading["id"])):
            return {
                "reading": None,
                "result": {"status": "CASE_ALREADY_PROCESSING"},
            }
        reading["status"] = "PROCESSING"
        return {"reading": reading}

    @staticmethod
    def _route_after_fetch(state: GraphState) -> str:
        return "case" if state.get("reading") else "none"

    @staticmethod
    def _validate_case(state: GraphState) -> GraphState:
        reading = state["reading"]
        assert reading is not None
        errors = validate_reading(reading)
        if errors:
            return {
                "validation_errors": errors,
                "specialist_results": [],
                "final_decision": {
                    "prediction": None,
                    "confidence": None,
                    "reason": "; ".join(errors),
                },
            }
        return {"validation_errors": []}

    @staticmethod
    def _route_after_validation(state: GraphState) -> str:
        return "invalid" if state.get("validation_errors") else "valid"

    def _run_specialist_tools(self, state: GraphState) -> GraphState:
        reading = state["reading"]
        assert reading is not None
        values = {biomarker: float(reading[biomarker]) for biomarker in BIOMARKERS}
        results = [self.scoring.evaluate(organ, values) for organ in ORGANS]
        return {"specialist_results": results}

    def _make_llm_decision(self, state: GraphState) -> GraphState:
        reading = state["reading"]
        assert reading is not None

        try:
            decision, model, raw_result = self.decision_maker.decide(
                reading,
                state["specialist_results"],
            )
        except OpenRouterDecisionError:
            self.database.release_reading(int(reading["id"]))
            return {
                "final_decision": None,
                "result": {
                    "status": "RETRY_REQUIRED",
                    "case_id": reading["case_id"],
                    "message": (
                        "The AI decision was not saved. The case remains NEW; "
                        "check the OpenRouter key/model access and run process again."
                    ),
                },
            }

        return {
            "selected_model": model,
            "llm_result": raw_result,
            "final_decision": decision,
        }

    @staticmethod
    def _route_after_llm(state: GraphState) -> str:
        return "success" if state.get("final_decision") else "failed"

    def _save_decision(self, state: GraphState) -> GraphState:
        reading = state["reading"]
        assert reading is not None

        if state.get("validation_errors"):
            with self.database.connect() as connection:
                connection.execute(
                    """
                    UPDATE readings
                    SET status = 'RETEST_REQUIRED', ai_prediction = NULL,
                        ai_confidence = NULL, ai_reason = ?
                    WHERE id = ?
                    """,
                    ("; ".join(state["validation_errors"]), reading["id"]),
                )
                connection.commit()
            return {
                "result": {
                    "status": "RETEST_REQUIRED",
                    "case_id": reading["case_id"],
                    "reason": "; ".join(state["validation_errors"]),
                }
            }

        decision = state["final_decision"]
        assert decision is not None
        selected_model = state.get("selected_model")
        raw_result = state.get("llm_result")
        assert selected_model is not None
        assert raw_result is not None

        self.database.persist_decision(
            reading=reading,
            decision=decision,
            specialist_results=state["specialist_results"],
            selected_model=selected_model,
            llm_result=raw_result,
        )

        return {
            "result": {
                "status": "PROCESSED",
                "case_id": reading["case_id"],
                "ai_prediction": decision["prediction"],
                "ai_confidence": decision["confidence"],
                "ai_reason": decision["reason"],
            }
        }

    def process_latest(self) -> dict[str, Any]:
        final_state = self.graph.invoke({})
        return final_state.get("result", {"status": "UNKNOWN"})


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "NOVERA LangGraph + SQLite screening core: deterministic specialist "
            "scoring and one OpenRouter decision call."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "init-db",
        help="Create or migrate the SQLite database and load reference ranges.",
    )

    add_parser = subparsers.add_parser("add-reading", help="Insert one NEW reading.")
    add_parser.add_argument("--ph", type=float, required=True)
    add_parser.add_argument("--urea", type=float, required=True, dest="urea_mg_dl")
    add_parser.add_argument(
        "--creatinine",
        type=float,
        required=True,
        dest="creatinine_umol_l",
    )
    add_parser.add_argument(
        "--temperature",
        type=float,
        required=True,
        dest="temperature_c",
    )

    subparsers.add_parser(
        "process",
        help="Process only the latest NEW reading using one OpenRouter call.",
    )

    confirm_parser = subparsers.add_parser(
        "confirm",
        help="Save the real human confirmation for a case.",
    )
    confirm_parser.add_argument("--case-id", required=True)
    confirm_parser.add_argument("--organ", required=True, choices=ORGANS)
    confirm_parser.add_argument("--confirmed-by", default=None)
    confirm_parser.add_argument("--notes", default=None)

    show_parser = subparsers.add_parser("show", help="Show one clean case record.")
    show_parser.add_argument("--case-id", required=True)

    list_parser = subparsers.add_parser("list", help="List recent case records.")
    list_parser.add_argument("--limit", type=int, default=20)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        service = NoveraService()

        if args.command == "init-db":
            print(
                json.dumps(
                    {
                        "status": "DATABASE_READY",
                        "database": str(DATABASE_PATH),
                    },
                    indent=2,
                )
            )

        elif args.command == "add-reading":
            case_id = service.database.add_reading(
                ph=args.ph,
                urea_mg_dl=args.urea_mg_dl,
                creatinine_umol_l=args.creatinine_umol_l,
                temperature_c=args.temperature_c,
            )
            print(
                json.dumps(
                    {
                        "status": "NEW_READING_ADDED",
                        "case_id": case_id,
                    },
                    indent=2,
                )
            )

        elif args.command == "process":
            print(
                json.dumps(
                    service.process_latest(),
                    indent=2,
                    ensure_ascii=False,
                )
            )

        elif args.command == "confirm":
            result = service.database.confirm_case(
                case_id=args.case_id,
                organ=args.organ,
                confirmed_by=args.confirmed_by,
                notes=args.notes,
            )
            print(json.dumps(result, indent=2, ensure_ascii=False))

        elif args.command == "show":
            result = service.database.get_case(args.case_id)
            if result is None:
                raise ValueError(f"Case not found: {args.case_id}")
            print(json.dumps(result, indent=2, ensure_ascii=False))

        elif args.command == "list":
            print(
                json.dumps(
                    service.database.list_cases(args.limit),
                    indent=2,
                    ensure_ascii=False,
                )
            )

        return 0

    except Exception as exc:
        # The CLI intentionally avoids exposing provider exception classes,
        # stack traces, tokens, or internal implementation details.
        print(
            json.dumps(
                {
                    "status": "ERROR",
                    "message": str(exc),
                },
                indent=2,
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
