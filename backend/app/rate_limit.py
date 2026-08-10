"""Shared slowapi Limiter instance — separate module so both main.py (setup)
and individual routers (the @limiter.limit(...) decorator) can import it
without a circular import."""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
