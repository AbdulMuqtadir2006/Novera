"""Admin/demo account support (2026-08-23, Hassan's call).

config.ADMIN_EMAIL, if set, names a real account (created once via
scripts/create_admin_account.py — never via this module) that should always
have at least one biomarker reading on file, so every feature (dashboard,
reports, self-care, voice, screening, WhatsApp) works for testing/demos
even with no sensor connected and no real test ever taken. Scoped strictly
to that one configured account — a real patient with zero readings still
sees the normal empty state everywhere, completely unchanged; see
reference_data.get_latest_row/get_reading_history for the two call sites
that hook this in.

The admin user_id is resolved from ADMIN_EMAIL once and cached in-process
(module-level) rather than re-querying on every call — cheap for everyone
else (a single int compare, no DB round trip, and a no-op entirely when
ADMIN_EMAIL is unset) and self-corrects if the account doesn't exist yet
(cache stays unset, retried on the next call — costs nothing once
ADMIN_EMAIL is unset, and only a few duplicate lookups in the window before
scripts/create_admin_account.py has actually been run).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from .. import config, db
from . import reading_synthesis

_admin_user_id: Optional[int] = None


def admin_user_id() -> Optional[int]:
    global _admin_user_id
    if not config.ADMIN_EMAIL:
        return None
    if _admin_user_id is None:
        row = db.fetch_one("SELECT id FROM users WHERE email = %s", (config.ADMIN_EMAIL,))
        if row:
            _admin_user_id = row["id"]
    return _admin_user_id


def is_admin_account(user_id: Optional[int]) -> bool:
    return user_id is not None and user_id == admin_user_id()


def ensure_seeded(user_id: int) -> Optional[dict[str, Any]]:
    """Inserts one synthetic reading for the admin account if it has none
    yet, returning the new row. No-op (returns None) for every other
    account. Only ever called from reference_data's own get_latest_row/
    get_reading_history when their real query already came back empty —
    never speculative, so this never runs for a normal patient even by
    accident."""
    if not is_admin_account(user_id):
        return None
    values = reading_synthesis.synthesize(last=None)
    return db.fetch_one(
        """
        INSERT INTO readings (user_id, "timestamp", ph, creatinine, urea, temperature)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (user_id, datetime.now(timezone.utc), values["ph"], values["creatinine"], values["urea"], values["temperature"]),
    )
