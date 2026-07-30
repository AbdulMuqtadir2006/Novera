#!/usr/bin/env python
"""Idempotent database initialization.

Creates all tables (db/schema.sql), seeds the reference_ranges lookup table,
and — unless the readings table already has rows, or --no-seed-readings is
passed — seeds ~30 days of demo dashboard readings so a fresh environment
has something to look at. Safe to re-run.

Usage (from backend/):
    python scripts/init_db.py
    python scripts/init_db.py --no-seed-readings
"""
from __future__ import annotations

import argparse
import math
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402
from app.core import scoring  # noqa: E402


def seed_reference_ranges() -> None:
    for organ, biomarkers in scoring.DEFAULT_REFERENCE_RANGES.items():
        for biomarker, (min_value, max_value, weight) in biomarkers.items():
            db.execute(
                """
                INSERT INTO reference_ranges (organ, biomarker, min_value, max_value, weight)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (organ, biomarker) DO UPDATE SET
                    min_value = excluded.min_value,
                    max_value = excluded.max_value,
                    weight = excluded.weight
                """,
                (organ, biomarker, min_value, max_value, weight),
            )
    print("Seeded reference_ranges.")


def seed_demo_readings(days: int = 30, force: bool = False) -> None:
    existing = db.fetch_one("SELECT COUNT(*) AS c FROM readings")["c"]
    if existing and not force:
        print(f"readings already has {existing} rows — skipping demo seed (pass --force-readings to reseed).")
        return
    if force:
        db.execute("DELETE FROM readings")

    rng = random.Random(42)
    end = datetime.now(timezone.utc)
    for i in range(days - 1, -1, -1):
        phase = (days - i) / days
        ts = (end - timedelta(days=i)).replace(hour=9, minute=14, second=0, microsecond=0)
        ph = round(6.7 + math.sin(phase * 6) * 0.35 + (rng.random() - 0.5) * 0.25, 2)
        creatinine = round(0.95 + math.sin(phase * 4 + 1) * 0.18 + (rng.random() - 0.5) * 0.12, 2)
        urea = round(18 + phase * 8 + math.sin(phase * 5) * 3 + (rng.random() - 0.5) * 3, 1)
        temperature = round(36.8 + math.sin(phase * 3) * 0.25 + (rng.random() - 0.5) * 0.2, 1)
        db.execute(
            'INSERT INTO readings ("timestamp", ph, creatinine, urea, temperature) VALUES (%s, %s, %s, %s, %s)',
            (ts, ph, creatinine, urea, temperature),
        )
    print(f"Seeded {days} demo dashboard readings.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize the NOVERA Postgres database.")
    parser.add_argument("--no-seed-readings", action="store_true", help="Skip demo dashboard readings entirely.")
    parser.add_argument("--force-readings", action="store_true", help="Delete and reseed demo readings even if some exist.")
    args = parser.parse_args()

    print("Creating schema...")
    db.init_schema()

    print("Seeding reference ranges...")
    seed_reference_ranges()

    if not args.no_seed_readings:
        seed_demo_readings(force=args.force_readings)

    print("Done.")


if __name__ == "__main__":
    main()
