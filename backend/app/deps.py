"""FastAPI auth dependencies — bearer token -> user (or None)."""
from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException

from . import security


def get_token(authorization: Optional[str] = Header(default=None)) -> Optional[str]:
    if authorization and authorization.startswith("Bearer "):
        return authorization[len("Bearer "):]
    return None


def get_current_user(authorization: Optional[str] = Header(default=None)) -> Optional[dict]:
    """Attaches the user if a valid Bearer token is present; None otherwise."""
    return security.get_user_by_token(get_token(authorization))


def require_user(authorization: Optional[str] = Header(default=None)) -> dict:
    user = get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
