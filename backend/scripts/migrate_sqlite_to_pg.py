#!/usr/bin/env python
"""Migrate legacy screening cases from SQLite (novera.py's novera.db) into
Postgres (req 4). Copies screening_cases + their confirmed_cases and
decision_audit rows for case_id in the given N-number window (default
N001-N150). Idempotent — `ON CONFLICT (case_id) DO NOTHING`, safe to re-run;
confirmed_cases/decision_audit are only inserted for readings that were
actually new this run, so re-running never creates duplicate audit rows.

Usage (from backend/):
    python scripts/migrate_sqlite_to_pg.py --sqlite-path "../.migration_scratch/legacy_novera.db"
    python scripts/migrate_sqlite_to_pg.py --sqlite-path <path> --start 1 --end 150
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402


def _open_sqlite(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def migrate(sqlite_path: Path, start: int, end: int) -> None:
    src = _open_sqlite(sqlite_path)
    rows = src.execute(
        """
        SELECT id, case_id, ph, urea_mg_dl, creatinine_umol_l, temperature_c,
               status, ai_prediction, ai_confidence, ai_reason, human_confirmation
        FROM readings
        WHERE case_id GLOB 'N[0-9][0-9][0-9]'
        ORDER BY id
        """
    ).fetchall()

    windowed = [r for r in rows if start <= int(r["case_id"][1:]) <= end]
    print(f"Found {len(rows)} case rows in source; {len(windowed)} fall in N{start:03d}-N{end:03d}.")

    inserted = 0
    skipped = 0
    old_id_to_new: dict[int, int] = {}

    for r in windowed:
        new_row = db.fetch_one(
            """
            INSERT INTO screening_cases (
                case_id, ph, urea_mg_dl, creatinine_umol_l, temperature_c,
                status, ai_prediction, ai_confidence, ai_reason, human_confirmation
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (case_id) DO NOTHING
            RETURNING id
            """,
            (
                r["case_id"], r["ph"], r["urea_mg_dl"], r["creatinine_umol_l"], r["temperature_c"],
                r["status"], r["ai_prediction"], r["ai_confidence"], r["ai_reason"], r["human_confirmation"],
            ),
        )
        if new_row:
            inserted += 1
            old_id_to_new[r["id"]] = new_row["id"]
        else:
            skipped += 1

    print(f"screening_cases: inserted {inserted}, skipped {skipped} (already present).")

    if not old_id_to_new:
        print("Nothing new to carry over for confirmed_cases / decision_audit.")
        return

    confirmed_rows = src.execute(
        f"SELECT reading_id, organ, notes, confirmed_by FROM confirmed_cases "
        f"WHERE reading_id IN ({','.join('?' * len(old_id_to_new))})",
        list(old_id_to_new.keys()),
    ).fetchall()
    confirmed_count = 0
    for c in confirmed_rows:
        db.execute(
            """
            INSERT INTO confirmed_cases (reading_id, organ, notes, confirmed_by)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (reading_id) DO NOTHING
            """,
            (old_id_to_new[c["reading_id"]], c["organ"], c["notes"], c["confirmed_by"]),
        )
        confirmed_count += 1
    print(f"confirmed_cases: carried over {confirmed_count}.")

    audit_rows = src.execute(
        f"SELECT reading_id, selected_model, llm_used, specialist_results_json, llm_result_json, "
        f"final_prediction, final_confidence, final_reason FROM decision_audit "
        f"WHERE reading_id IN ({','.join('?' * len(old_id_to_new))})",
        list(old_id_to_new.keys()),
    ).fetchall()
    for a in audit_rows:
        db.execute(
            """
            INSERT INTO decision_audit (
                reading_id, selected_model, llm_used, specialist_results_json,
                llm_result_json, final_prediction, final_confidence, final_reason
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                old_id_to_new[a["reading_id"]], a["selected_model"], a["llm_used"],
                json.dumps(json.loads(a["specialist_results_json"])),
                json.dumps(json.loads(a["llm_result_json"])) if a["llm_result_json"] else None,
                a["final_prediction"], a["final_confidence"], a["final_reason"],
            ),
        )
    print(f"decision_audit: carried over {len(audit_rows)}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate legacy SQLite screening cases into Postgres.")
    parser.add_argument("--sqlite-path", required=True, help="Path to the legacy novera.db")
    parser.add_argument("--start", type=int, default=1, help="First N-number to migrate (default 1)")
    parser.add_argument("--end", type=int, default=150, help="Last N-number to migrate (default 150)")
    args = parser.parse_args()

    sqlite_path = Path(args.sqlite_path).resolve()
    if not sqlite_path.exists():
        raise SystemExit(f"SQLite file not found: {sqlite_path}")

    db.init_schema()  # make sure the target tables exist
    migrate(sqlite_path, args.start, args.end)


if __name__ == "__main__":
    main()
