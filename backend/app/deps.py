"""FastAPI auth dependencies — bearer token -> user (or None)."""
from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException

from . import config, security


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


def require_device_key(x_device_key: Optional[str] = Header(default=None)) -> None:
    """Gate for the two endpoints the physical ESP32 hits with no user session
    (POST /readings, POST /device/ping) — see config.DEVICE_API_KEY. No-op
    (feature off) when the key isn't configured yet, so this can't lock out the
    real device before it's been reflashed with a matching key."""
    if config.DEVICE_API_KEY and x_device_key != config.DEVICE_API_KEY:
        raise HTTPException(status_code=401, detail="Not authenticated")
