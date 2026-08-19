"""Thawani (Oman) checkout-session client.

Thawani has no official Python SDK — this hand-rolled client mirrors the
REST contract read directly from Thawani's own open-source WooCommerce
plugin (github.com/PhazeRoOman/thawani-for-woocommerce, src/RestAPI.php +
src/Endpoint/Session.php + src/WC_Gateway_ThawaniGateway.php), a real
production integration, rather than guessed. Contract:

  POST {base}/api/v1/checkout/session
    headers: {"Thawani-Api-Key": secret_key, "Content-Type": "application/json"}
    body: {client_reference_id, products: [{name, unit_amount (int, baisa), quantity}],
           success_url, cancel_url, metadata}
    -> {"success": true, "data": {"session_id": "..."}}

  GET {base}/api/v1/checkout/session/{session_id}
    headers: {"Thawani-Api-Key": secret_key}
    -> {"success": true, "data": {"payment_status": "unpaid"|"paid"|"cancelled", ...}}

  Customer-facing redirect URL: {base}/pay/{session_id}?key={publishable_key}

No signature-verified webhook is used here (same choice the reference
plugin makes) — after Thawani redirects the browser back to our
success_url/cancel_url, the backend does its own authenticated GET on the
session before ever marking an order paid, so a spoofed redirect can't
fake a payment; only Thawani's own API, called with our secret key, is
trusted as the source of truth.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import requests

from .. import config

logger = logging.getLogger(__name__)

DEV_ENDPOINT = "https://uatcheckout.thawani.om"
PROD_ENDPOINT = "https://checkout.thawani.om"


class ThawaniError(RuntimeError):
    """Raised when Thawani doesn't return a usable session."""


def _base_url() -> str:
    return PROD_ENDPOINT if config.THAWANI_ENV.strip().lower() == "production" else DEV_ENDPOINT


def _headers() -> dict[str, str]:
    return {"Content-Type": "application/json", "Thawani-Api-Key": config.THAWANI_SECRET_KEY}


def create_session(
    *,
    client_reference_id: str,
    products: list[dict[str, Any]],
    success_url: str,
    cancel_url: str,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """products: [{"name": str, "unit_amount": int (baisa), "quantity": int}, ...].
    Returns {"session_id": str, "checkout_url": str}."""
    if not config.THAWANI_ENABLED:
        raise ThawaniError("Thawani is not configured (THAWANI_SECRET_KEY/THAWANI_PUBLISHABLE_KEY unset).")

    payload = {
        "client_reference_id": client_reference_id,
        "products": products,
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata": metadata or {},
    }
    try:
        resp = requests.post(f"{_base_url()}/api/v1/checkout/session", json=payload, headers=_headers(), timeout=20)
        data = resp.json()
    except Exception as exc:
        raise ThawaniError(f"Could not reach Thawani: {exc}") from exc

    if not data.get("success") or not data.get("data", {}).get("session_id"):
        raise ThawaniError(f"Thawani session creation failed: {data.get('description') or data}")

    session_id = data["data"]["session_id"]
    checkout_url = f"{_base_url()}/pay/{session_id}?key={config.THAWANI_PUBLISHABLE_KEY}"
    logger.info("thawani: created session_id=%s for client_reference_id=%s", session_id, client_reference_id)
    return {"session_id": session_id, "checkout_url": checkout_url}


def get_session_status(session_id: str) -> str:
    """Returns Thawani's own payment_status string: 'unpaid' | 'paid' | 'cancelled'.
    Always call this before marking an order paid — never trust the mere
    fact that the browser was redirected to success_url."""
    if not config.THAWANI_ENABLED:
        raise ThawaniError("Thawani is not configured.")
    try:
        resp = requests.get(f"{_base_url()}/api/v1/checkout/session/{session_id}", headers=_headers(), timeout=20)
        data = resp.json()
    except Exception as exc:
        raise ThawaniError(f"Could not reach Thawani: {exc}") from exc

    if not data.get("success"):
        raise ThawaniError(f"Thawani session lookup failed: {data.get('description') or data}")
    return str(data.get("data", {}).get("payment_status", "unpaid")).lower()
