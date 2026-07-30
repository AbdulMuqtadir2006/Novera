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
from typing import Any

from .. import config, db

ORGANS = ("KIDNEY", "STOMACH", "ORAL")
BIOMARKERS = ("ph", "urea_mg_dl", "creatinine_umol_l", "temperature_c")

# Canonical reference ranges — the same values novera.py has always used, and
# that the migrated N001-N150 confirmed cases were labelled against.
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


def _value_fit(value: float, spec: RangeSpec) -> tuple[float, str, float]:
    width = max(spec.max_value - spec.min_value, 1e-9)
    if spec.min_value <= value <= spec.max_value:
        midpoint = (spec.min_value + spec.max_value) / 2.0
        half_width = width / 2.0
        centrality = 1.0 - min(abs(value - midpoint) / max(half_width, 1e-9), 1.0)
        return 0.85 + 0.15 * centrality, "inside", 0.0

    distance = spec.min_value - value if value < spec.min_value else value - spec.max_value
    normalized_deviation = distance / width
    score = max(0.0, 0.85 - normalized_deviation)
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

def add_reading(ph: float, urea_mg_dl: float, creatinine_umol_l: float, temperature_c: float) -> str:
    """Insert one NEW screening case and generate the next N-number case ID."""
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
                INSERT INTO screening_cases (case_id, ph, urea_mg_dl, creatinine_umol_l, temperature_c, status)
                VALUES (%s, %s, %s, %s, %s, 'NEW')
                """,
                (case_id, ph, urea_mg_dl, creatinine_umol_l, temperature_c),
            )
    return case_id


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
