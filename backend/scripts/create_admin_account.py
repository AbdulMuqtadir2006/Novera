#!/usr/bin/env python
"""Creates or updates the admin/demo account — see core/demo_account.py and
config.py's ADMIN_EMAIL/ADMIN_WA_TRIGGER_PHRASE docs for what this account
is for (every feature works for it even with no real reading on file).

Never hardcodes the email/password/phone — all three come from CLI args or
env vars, so the actual credential never lives in a file checked into git.
Idempotent: if the email already exists, updates its password (and name, if
given) instead of failing.

Usage (from backend/, against whichever DATABASE_URL is in your environment
— e.g. run once via `railway run` against the production database):
    python scripts/create_admin_account.py --email admin@echo-nova.online --phone +9680000001

Omit --password to be prompted for it interactively (keeps it out of shell
history). After running, set ADMIN_EMAIL to the same email in the backend's
own environment (Railway variables) to actually activate the feature —
creating the account alone does nothing until that's set.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db, security  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", default=os.getenv("ADMIN_EMAIL", ""), help="Must match ADMIN_EMAIL in the backend's own environment.")
    parser.add_argument("--password", default=os.getenv("ADMIN_PASSWORD", ""), help="Prompted for interactively if omitted.")
    parser.add_argument("--phone", default=os.getenv("ADMIN_PHONE", ""), help="Required by the users table; doesn't need to be a real device unless you also want it recognized without the WhatsApp trigger phrase.")
    parser.add_argument("--name", default=os.getenv("ADMIN_NAME", "NOVERA Demo Account"))
    args = parser.parse_args()

    email = (args.email or "").strip().lower()
    if not email:
        sys.exit("Provide --email or set ADMIN_EMAIL.")
    phone = (args.phone or "").strip()
    if not phone:
        sys.exit("Provide --phone or set ADMIN_PHONE.")
    password = args.password or getpass.getpass("Admin password: ")
    if not password:
        sys.exit("A password is required.")

    existing = db.fetch_one("SELECT id FROM users WHERE email = %s", (email,))
    if existing:
        security.set_password(existing["id"], password)
        if args.name and args.name != "NOVERA Demo Account":
            db.execute("UPDATE users SET name = %s WHERE id = %s", (args.name, existing["id"]))
        print(f"Updated password for existing admin account (user_id={existing['id']}, email={email}).")
        return

    user = security.create_user(args.name, email, password, phone)
    print(f"Created admin account: id={user['id']}, email={user['email']}, phone={user['phone']}")
    print("Now set ADMIN_EMAIL to this same email in the backend's environment (Railway Variables) to activate it.")


if __name__ == "__main__":
    main()
