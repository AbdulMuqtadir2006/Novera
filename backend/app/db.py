"""Postgres access (psycopg3 + a connection pool).

The pool is constructed but never opened at import time — opening (which
touches the network) happens lazily on first real use. This means
`import app.main` succeeds even with no reachable database, which is what
lets the backend's syntax/imports be verified without a live Postgres.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional, Sequence

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from . import config

BACKEND_ROOT = Path(__file__).resolve().parent.parent

_pool: Optional[ConnectionPool] = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        if not config.DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not configured.")
        _pool = ConnectionPool(
            config.DATABASE_URL,
            open=False,
            # min_size/max_size (2026-08-23, perf pass): psycopg_pool's own
            # default is min_size=4 with max_size defaulting to min_size —
            # i.e. a hard ceiling of 4 concurrent connections for the whole
            # app. Multiple dashboard users each polling /readings/latest +
            # /device/status every few seconds (see frontend's useLatestReading/
            # useDeviceStatus hooks) can plausibly exceed that under real
            # concurrent load. Raised to a still-modest ceiling appropriate
            # for this app's scale, not a guess at a "correct" number.
            min_size=4,
            max_size=10,
            kwargs={"row_factory": dict_row, "autocommit": True},
        )
    if _pool.closed:  # only real connect happens here, on first use
        _pool.open(wait=True, timeout=15)
    return _pool


@contextmanager
def get_conn() -> Iterator[psycopg.Connection]:
    with get_pool().connection() as conn:
        yield conn


def fetch_one(sql: str, params: Sequence[Any] = ()) -> Optional[dict]:
    with get_conn() as conn:
        return conn.execute(sql, params).fetchone()


def fetch_all(sql: str, params: Sequence[Any] = ()) -> list[dict]:
    with get_conn() as conn:
        return conn.execute(sql, params).fetchall()


def execute(sql: str, params: Sequence[Any] = ()) -> None:
    with get_conn() as conn:
        conn.execute(sql, params)


def init_schema() -> None:
    """Run db/schema.sql (idempotent — CREATE ... IF NOT EXISTS throughout)."""
    ddl = (BACKEND_ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
    with get_conn() as conn:
        conn.execute(ddl)
