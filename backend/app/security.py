"""Auth — scrypt password hashing + opaque bearer session tokens.

Ported 1:1 from the previous Node backend's server/auth.js so existing
frontend behavior (login/signup/session) is unchanged (req 1). Demo-grade:
sufficient for a research/demo app, not a hardened production auth system.
"""
from __future__ import annotations

import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone
from hashlib import scrypt
from typing import Optional

from . import db

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+\d{8,15}$")
SESSION_LIFETIME = timedelta(days=30)


class AuthError(ValueError):
    pass


def _hash_password(password: str) -> tuple[str, str]:
    salt = secrets.token_hex(16)
    digest = scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1, dklen=64)
    return salt, digest.hex()


def _verify_password(password: str, salt: str, expected_hash: str) -> bool:
    digest = scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1, dklen=64)
    expected = bytes.fromhex(expected_hash)
    return hmac.compare_digest(digest, expected)


def normalize_phone(raw: Optional[str]) -> str:
    """Normalise a phone to "+<digits>" (defaults to Oman +968 when no country code)."""
    if not raw:
        return ""
    raw = str(raw).strip()
    had_plus = raw.startswith("+")
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("00"):
        digits = digits[2:]
    if had_plus:
        return "+" + digits
    if digits.startswith("968"):
        return "+" + digits
    digits = digits.lstrip("0")
    if len(digits) <= 9:
        return "+968" + digits
    return "+" + digits


def _public_user(row: Optional[dict]) -> Optional[dict]:
    if not row:
        return None
    return {"id": row["id"], "email": row["email"], "name": row["name"], "phone": row["phone"]}


def create_user(name: str, email: str, password: str, phone: str) -> dict:
    norm_email = (email or "").strip().lower()
    if not _EMAIL_RE.match(norm_email):
        raise AuthError("Invalid email")
    if not password or len(password) < 6:
        raise AuthError("Password must be at least 6 characters")
    norm_phone = normalize_phone(phone)
    if not _PHONE_RE.match(norm_phone):
        raise AuthError("Invalid phone number (include country code, e.g. +968...)")

    existing = db.fetch_one("SELECT id FROM users WHERE email = %s", (norm_email,))
    if existing:
        raise AuthError("An account with this email already exists")

    salt, pass_hash = _hash_password(password)
    row = db.fetch_one(
        """
        INSERT INTO users (email, name, phone, pass_salt, pass_hash)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id, email, name, phone
        """,
        (norm_email, (name or "").strip(), norm_phone, salt, pass_hash),
    )
    return _public_user(row)


def authenticate(email: str, password: str) -> Optional[dict]:
    row = db.fetch_one(
        "SELECT * FROM users WHERE email = %s",
        ((email or "").strip().lower(),),
    )
    if not row or not _verify_password(password, row["pass_salt"], row["pass_hash"]):
        return None
    return _public_user(row)


def create_session(user_id: int) -> str:
    token = secrets.token_hex(32)
    expires_at = datetime.now(timezone.utc) + SESSION_LIFETIME
    db.execute(
        "INSERT INTO sessions (token, user_id, expires_at) VALUES (%s, %s, %s)",
        (token, user_id, expires_at),
    )
    return token


def get_user_by_token(token: Optional[str]) -> Optional[dict]:
    if not token:
        return None
    row = db.fetch_one(
        """
        SELECT u.* FROM sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.token = %s AND s.expires_at > now()
        """,
        (token,),
    )
    return _public_user(row)


def delete_session(token: Optional[str]) -> None:
    if token:
        db.execute("DELETE FROM sessions WHERE token = %s", (token,))
