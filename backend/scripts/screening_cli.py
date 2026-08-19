#!/usr/bin/env python
"""Ops CLI for the screening pipeline — add-reading / process / confirm /
show / list. Ported from novera.py's original argparse CLI, now against
Postgres. Useful for manually confirming cases (building similarity-scoring
memory) without a UI, since no frontend page exposes case confirmation.

Usage (from backend/):
    python scripts/screening_cli.py add-reading --ph 6.8 --urea 24 --creatinine 20 --temperature 36.8
    python scripts/screening_cli.py process
    python scripts/screening_cli.py confirm --case-id N151 --organ KIDNEY --confirmed-by Dr.Amal
    python scripts/screening_cli.py show --case-id N151
    python scripts/screening_cli.py list --limit 20
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402
from app.core import scoring, screening_llm  # noqa: E402


def confirm_case(case_id: str, organ: str, confirmed_by: str | None, notes: str | None) -> dict:
    organ = organ.upper()
    if organ not in scoring.ORGANS:
        raise ValueError(f"organ must be one of: {', '.join(scoring.ORGANS)}")

    reading = db.fetch_one("SELECT id, ai_prediction FROM screening_cases WHERE case_id = %s", (case_id,))
    if not reading:
        raise ValueError(f"Case not found: {case_id}")

    db.execute(
        """
        INSERT INTO confirmed_cases (reading_id, organ, notes, confirmed_by)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (reading_id) DO UPDATE SET
            organ = excluded.organ, notes = excluded.notes, confirmed_by = excluded.confirmed_by
        """,
        (reading["id"], organ, notes, confirmed_by),
    )
    db.execute("UPDATE screening_cases SET human_confirmation = %s WHERE id = %s", (organ, reading["id"]))

    return {
        "case_id": case_id,
        "ai_prediction": reading["ai_prediction"],
        "human_confirmation": organ,
        "matches_ai": None if reading["ai_prediction"] not in scoring.ORGANS else reading["ai_prediction"] == organ,
    }


def get_case(case_id: str) -> dict | None:
    return db.fetch_one(
        """
        SELECT case_id, ph, urea_mg_dl, creatinine_umol_l, temperature_c, status,
               ai_prediction, ai_confidence, ai_reason, human_confirmation
        FROM screening_cases WHERE case_id = %s
        """,
        (case_id,),
    )


def list_cases(limit: int) -> list[dict]:
    return db.fetch_all(
        """
        SELECT case_id, status, ai_prediction, ai_confidence, human_confirmation
        FROM screening_cases ORDER BY id DESC LIMIT %s
        """,
        (max(1, limit),),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NOVERA screening pipeline ops CLI (Postgres).")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="Create tables + seed reference ranges.")

    add_p = sub.add_parser("add-reading", help="Insert one NEW screening case.")
    add_p.add_argument("--user-id", type=int, default=None, help="Owning user id (multi-tenant, 2026-08-19) — omit for an orphaned/unowned test case")
    add_p.add_argument("--ph", type=float, required=True)
    add_p.add_argument("--urea", type=float, required=True, dest="urea_mg_dl")
    add_p.add_argument("--creatinine", type=float, required=True, dest="creatinine_umol_l")
    add_p.add_argument("--temperature", type=float, required=True, dest="temperature_c")

    sub.add_parser("process", help="Process only the latest NEW case (one OpenRouter call).")

    confirm_p = sub.add_parser("confirm", help="Save the real human confirmation for a case.")
    confirm_p.add_argument("--case-id", required=True)
    confirm_p.add_argument("--organ", required=True, choices=scoring.ORGANS)
    confirm_p.add_argument("--confirmed-by", default=None)
    confirm_p.add_argument("--notes", default=None)

    show_p = sub.add_parser("show", help="Show one case record.")
    show_p.add_argument("--case-id", required=True)

    list_p = sub.add_parser("list", help="List recent case records.")
    list_p.add_argument("--limit", type=int, default=20)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "init-db":
            db.init_schema()
            print(json.dumps({"status": "DATABASE_READY"}, indent=2))
        elif args.command == "add-reading":
            case_id = scoring.add_reading(args.user_id, args.ph, args.urea_mg_dl, args.creatinine_umol_l, args.temperature_c)
            print(json.dumps({"status": "NEW_READING_ADDED", "case_id": case_id}, indent=2))
        elif args.command == "process":
            print(json.dumps(screening_llm.process_latest(), indent=2, ensure_ascii=False))
        elif args.command == "confirm":
            print(json.dumps(confirm_case(args.case_id, args.organ, args.confirmed_by, args.notes), indent=2, ensure_ascii=False))
        elif args.command == "show":
            result = get_case(args.case_id)
            if result is None:
                raise ValueError(f"Case not found: {args.case_id}")
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        elif args.command == "list":
            print(json.dumps(list_cases(args.limit), indent=2, ensure_ascii=False, default=str))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "ERROR", "message": str(exc)}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
