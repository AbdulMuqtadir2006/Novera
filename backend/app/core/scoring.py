"""Deterministic organ-screening scoring engine.

Ported 1:1 from the standalone novera.py core (range score + similarity
score against a limited, SQL-bounded set of confirmed cases). This is the
only place screening math lives — the OpenRouter call in screening_llm.py
makes exactly one decision from these numbers, never invents thresholds.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Optional

import psycopg

from .. import config, db
from . import reference_data

ORGANS = ("KIDNEY", "LIVER", "ORAL")
BIOMARKERS = ("ph", "urea_mg_dl", "creatinine_umol_l", "temperature_c")
CREATININE_MGDL_TO_UMOLL = 88.42

# Canonical reference ranges — the same values novera.py has always used, and
# that the migrated N001-N150 confirmed cases were labelled against.
DEFAULT_REFERENCE_RANGES: dict[str, dict[str, tuple[float, float, float]]] = {
    "KIDNEY": {
        "ph": (6.2, 7.6, 1.0),
        "urea_mg_dl": (20.0, 30.0, 1.2),
        "creatinine_umol_l": (18.0, 25.0, 1.3),
        "temperature_c": (35.0, 37.0, 0.8),
    },
    "LIVER": {
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


@dataclass(frozen=True)
class RangeSpec:
    min_value: float
    max_value: float
    weight: float


# Cached at startup (req 9) — avoids hitting reference_ranges on every request.
_RANGE_CACHE: dict[str, dict[str, RangeSpec]] | None = None


def load_reference_ranges(force: bool = False) -> dict[str, dict[str, RangeSpec]]:
    global _RANGE_CACHE
    if _RANGE_CACHE is not None and not force:
        return _RANGE_CACHE

    rows = db.fetch_all(
        "SELECT organ, biomarker, min_value, max_value, weight FROM reference_ranges ORDER BY organ, biomarker"
    )
    ranges: dict[str, dict[str, RangeSpec]] = {organ: {} for organ in ORGANS}
    for row in rows:
        ranges[row["organ"]][row["biomarker"]] = RangeSpec(
            min_value=float(row["min_value"]),
            max_value=float(row["max_value"]),
            weight=float(row["weight"]),
        )

    for organ in ORGANS:
        missing = set(BIOMARKERS) - set(ranges[organ])
        if missing:
            raise RuntimeError(f"Reference ranges are incomplete for {organ}: {sorted(missing)}")

    _RANGE_CACHE = ranges
    return ranges


def fetch_confirmed_cases(organ: str, limit: int) -> list[dict[str, Any]]:
    """Query only a limited, organ-specific subset from confirmed memory (req 9)."""
    return db.fetch_all(
        """
        SELECT r.id, r.case_id, r.ph, r.urea_mg_dl, r.creatinine_umol_l, r.temperature_c
        FROM confirmed_cases AS c
        JOIN screening_cases AS r ON r.id = c.reading_id
        WHERE c.organ = %s
        ORDER BY c.id DESC
        LIMIT %s
        """,
        (organ, limit),
    )


EDGE_OF_RANGE_SCORE = 0.35  # concern score right at the boundary of "inside" — see note below

def _value_fit(value: float, spec: RangeSpec) -> tuple[float, str, float]:
    """Returns a *concern* score: low when the value sits comfortably inside
    the normal range, rising only as it approaches or crosses the edge.

    FIXED (found live, 2026-08-20): this used to score ANY in-range value at
    0.85-1.0 — i.e. being solidly, healthily centered in the normal range
    scored as strong evidence of a problem (0.85 already clears the "high"
    flag threshold of 0.80), while sitting at the edge of normal scored
    *lower*. That's inverted from what "normal range" should mean, and since
    KIDNEY/LIVER/ORAL's normal bands overlap heavily, it meant a
    genuinely healthy reading would still get forced onto whichever organ
    it happened to be nearest the center of, at flag=medium/high — which is
    exactly what triggers the WhatsApp outreach guarantee's appointment
    offer for a healthy patient. Now: 0 at the range's midpoint, rising to
    EDGE_OF_RANGE_SCORE at the boundary (deliberately still below the
    "medium" flag threshold of 0.60 - the edge of normal shouldn't itself
    read as concerning), and continuing to climb past the boundary using
    the same normalized-deviation math the "outside" branch already used,
    so the two branches meet continuously at the edge with no discontinuity.
    """
    width = max(spec.max_value - spec.min_value, 1e-9)
    if spec.min_value <= value <= spec.max_value:
        midpoint = (spec.min_value + spec.max_value) / 2.0
        half_width = width / 2.0
        centrality_gap = min(abs(value - midpoint) / max(half_width, 1e-9), 1.0)
        return EDGE_OF_RANGE_SCORE * centrality_gap**2, "inside", 0.0

    distance = spec.min_value - value if value < spec.min_value else value - spec.max_value
    normalized_deviation = distance / width
    score = min(1.0, EDGE_OF_RANGE_SCORE + normalized_deviation)
    flag = "borderline" if normalized_deviation <= 0.15 else "outside"
    return score, flag, normalized_deviation


class ScoringEngine:
    def __init__(self, ranges: dict[str, dict[str, RangeSpec]], confirmed_limit: int = None):
        self.ranges = ranges
        self.confirmed_limit = confirmed_limit or config.CONFIRMED_CASE_QUERY_LIMIT

    def _range_score(self, organ: str, values: dict[str, float]) -> tuple[float, dict[str, Any]]:
        weighted_total = 0.0
        total_weight = 0.0
        details: dict[str, Any] = {}
        for biomarker in BIOMARKERS:
            spec = self.ranges[organ][biomarker]
            score, flag, deviation = _value_fit(values[biomarker], spec)
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

    def _similarity_score(self, organ: str, values: dict[str, float]) -> tuple[float, int, list[dict[str, Any]]]:
        candidates = fetch_confirmed_cases(organ, self.confirmed_limit)
        similarities: list[dict[str, Any]] = []
        for case in candidates:
            squared_differences = []
            for biomarker in BIOMARKERS:
                spec = self.ranges[organ][biomarker]
                width = max(spec.max_value - spec.min_value, 1e-9)
                normalized_difference = (values[biomarker] - float(case[biomarker])) / width
                squared_differences.append(normalized_difference**2)
            distance = math.sqrt(sum(squared_differences) / len(squared_differences))
            similarity = 1.0 / (1.0 + distance)
            similarities.append({"case_id": case["case_id"], "similarity": round(similarity, 4), "distance": round(distance, 4)})

        similarities.sort(key=lambda item: item["similarity"], reverse=True)
        closest = similarities[:3]
        score = sum(item["similarity"] for item in closest) / len(closest) if closest else 0.0
        return score, len(candidates), closest

    def evaluate(self, organ: str, values: dict[str, float]) -> dict[str, Any]:
        range_score, biomarker_details = self._range_score(organ, values)
        similarity_score, candidate_count, closest_cases = self._similarity_score(organ, values)

        combined_score = (
            0.55 * range_score + 0.45 * similarity_score if candidate_count > 0 else range_score
        )
        flag = "high" if combined_score >= 0.80 else "medium" if combined_score >= 0.60 else "low"
        if config.SUPPRESS_SCREENING_FLAGS:
            # Temporary override (2026-08-20, Hassan's call) — sensors/
            # calibration aren't trustworthy enough yet to be telling real
            # people to get tested or see a doctor. combined_score itself
            # stays real (still stored in decision_audit for later
            # analysis); only the flag that whatsapp_gating and other
            # automation act on is forced down. See config.py.
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
        }


def get_engine() -> ScoringEngine:
    return ScoringEngine(load_reference_ranges())


# ---------------------------------------------------------------------------
# screening_cases persistence — ported from novera.py's Database class.
# ---------------------------------------------------------------------------

MAX_CASE_ID_ATTEMPTS = 5


def add_reading(user_id: int, ph: float, urea_mg_dl: float, creatinine_umol_l: float, temperature_c: float) -> str:
    """Insert one NEW screening case and generate the next N-number case ID.

    Bug fix (2026-08-22): the SELECT MAX + INSERT below isn't safe against a
    concurrent call landing in between (READ COMMITTED, Postgres's default,
    doesn't lock against that) — two racing calls can compute the same
    next_number, and the second INSERT used to throw an uncaught
    UniqueViolation (case_id is UNIQUE) straight up to whatever caller
    triggered it. Retries with a freshly recomputed number on conflict, same
    bounded-retry shape as core/booking.py's slot-booking loop."""
    for attempt in range(MAX_CASE_ID_ATTEMPTS):
        try:
            with db.get_conn() as conn:
                with conn.transaction():
                    row = conn.execute(
                        """
                        SELECT MAX((regexp_replace(case_id, '^N', ''))::int) AS max_number
                        FROM screening_cases
                        WHERE case_id ~ '^N[0-9]+$'
                        """
                    ).fetchone()
                    next_number = (row["max_number"] or 0) + 1
                    case_id = f"N{next_number:03d}"
                    conn.execute(
                        """
                        INSERT INTO screening_cases (user_id, case_id, ph, urea_mg_dl, creatinine_umol_l, temperature_c, status)
                        VALUES (%s, %s, %s, %s, %s, %s, 'NEW')
                        """,
                        (user_id, case_id, ph, urea_mg_dl, creatinine_umol_l, temperature_c),
                    )
            return case_id
        except psycopg.errors.UniqueViolation:
            if attempt == MAX_CASE_ID_ATTEMPTS - 1:
                raise
    raise RuntimeError("Could not generate a unique screening case id.")


def claim_new_case_from_latest_reading(user_id: int) -> dict[str, Any] | None:
    """Shared by the manual /predict-organ(/stream) endpoints (routers/screening.py)
    and the autonomous guidance agent (core/guidance_agent.py): turn this user's
    latest `readings` row into a freshly claimed 'PROCESSING' screening_cases row.

    Returns None (rather than raising) when there's no reading yet, since the two
    callers want different behavior for that case (HTTP 404 vs. silently skipping
    an orchestrator run) — the caller decides what "no reading" means for it.
    """
    row = reference_data.get_latest_row(user_id)
    if not row:
        return None
    reading = reference_data.row_to_reading(row)
    m = reading["metrics"]

    case_id = add_reading(
        user_id=user_id,
        ph=float(m["ph"]["value"]),
        urea_mg_dl=float(m["urea"]["value"]),
        creatinine_umol_l=float(m["creatinine"]["value"]) * CREATININE_MGDL_TO_UMOLL,
        temperature_c=float(m["temperature"]["value"]),
    )
    case_row = db.fetch_one(
        """
        SELECT id, case_id, ph, urea_mg_dl, creatinine_umol_l, temperature_c, status
        FROM screening_cases WHERE case_id = %s
        """,
        (case_id,),
    )
    claim_reading(case_row["id"])
    case_row["status"] = "PROCESSING"
    return case_row


def fetch_latest_new_reading() -> dict[str, Any] | None:
    return db.fetch_one(
        """
        SELECT id, case_id, ph, urea_mg_dl, creatinine_umol_l, temperature_c, status
        FROM screening_cases
        WHERE status = 'NEW'
        ORDER BY id DESC
        LIMIT 1
        """
    )


def claim_reading(reading_id: int) -> bool:
    with db.get_conn() as conn:
        cur = conn.execute(
            "UPDATE screening_cases SET status = 'PROCESSING' WHERE id = %s AND status = 'NEW'",
            (reading_id,),
        )
        return cur.rowcount == 1


def get_latest_screening_flag(user_id: int) -> Optional[dict[str, Any]]:
    """The flag (low/medium/high) for this user's most recently COMPLETED
    screening case — used by the WhatsApp Agent's outreach guarantee (spec
    §6), which needs to know whether the latest case was medium/high without
    recomputing the whole pipeline. Multi-tenant (2026-08-19): scoped to
    user_id — without this, a medium/high flag belonging to a different
    patient could force an appointment-offer message to the wrong person.
    `flag` itself is only ever stored inside decision_audit.
    specialist_results_json (per-organ), never as its own column on
    screening_cases, so this re-derives it the same way guidance_agent.py
    does at persist-time: look up the specialist result whose organ matches
    the final prediction."""
    row = db.fetch_one(
        """
        SELECT da.final_prediction, da.specialist_results_json, da.final_confidence,
               sc.case_id
        FROM decision_audit da
        JOIN screening_cases sc ON sc.id = da.reading_id
        WHERE sc.user_id = %s
        ORDER BY da.id DESC
        LIMIT 1
        """,
        (user_id,),
    )
    if not row:
        return None
    specialist_results = row["specialist_results_json"]
    if isinstance(specialist_results, str):
        specialist_results = json.loads(specialist_results)
    flag = next(
        (r["flag"] for r in specialist_results if r["organ"] == row["final_prediction"]),
        None,
    )
    if flag is None:
        return None
    return {
        "organ": row["final_prediction"],
        "flag": flag,
        "confidence": row["final_confidence"],
        "case_id": row["case_id"],
    }


def release_reading(reading_id: int) -> None:
    """Return a failed OpenRouter case to NEW without saving a fake prediction (req 8)."""
    db.execute(
        """
        UPDATE screening_cases
        SET status = 'NEW', ai_prediction = NULL, ai_confidence = NULL, ai_reason = NULL
        WHERE id = %s
        """,
        (reading_id,),
    )


def persist_decision(
    reading: dict[str, Any],
    decision: dict[str, Any],
    specialist_results: list[dict[str, Any]],
    selected_model: str,
    llm_result: dict[str, Any],
) -> None:
    prediction = str(decision["prediction"]).upper()
    if prediction not in ORGANS:
        raise ValueError("Only a single organ prediction can be saved.")

    with db.get_conn() as conn:
        with conn.transaction():
            conn.execute(
                """
                UPDATE screening_cases
                SET status = 'COMPLETED', ai_prediction = %s, ai_confidence = %s, ai_reason = %s
                WHERE id = %s
                """,
                (prediction, float(decision["confidence"]), str(decision["reason"]), reading["id"]),
            )
            conn.execute(
                """
                INSERT INTO decision_audit (
                    reading_id, selected_model, llm_used, specialist_results_json,
                    llm_result_json, final_prediction, final_confidence, final_reason
                ) VALUES (%s, %s, 1, %s, %s, %s, %s, %s)
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


def mark_retest_required(reading_id: int, reason: str) -> None:
    db.execute(
        """
        UPDATE screening_cases
        SET status = 'RETEST_REQUIRED', ai_prediction = NULL, ai_confidence = NULL, ai_reason = %s
        WHERE id = %s
        """,
        (reason, reading_id),
    )


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
            errors.append(f"{field} is outside the plausible input range {minimum}-{maximum}")
    return errors
