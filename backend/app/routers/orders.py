"""Store: NOVERA Reader + strip bundles. One-time purchases only, no
subscription anywhere in this router. Guest checkout is allowed (spec:
buying strips shouldn't require an account) — user_id is attached only if
the caller happens to be logged in.

Pricing is never trusted from the client — every checkout re-prices from
app/core/catalog.py server-side (the single source of truth). Device and
bundle line items are always kept separate (item_type), never collapsed
into one SKU, so device revenue and bundle revenue stay two distinct lines
for the financial model.
"""
from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse

from .. import config, db
from ..core import catalog, thawani
from ..deps import get_current_user
from ..schemas import CheckoutReq

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/catalog")
def get_catalog():
    return catalog.public_catalog()


def _order_out(order: dict, items: list[dict]) -> dict:
    return {
        "order_token": order["order_token"],
        "status": order["status"],
        "currency": order["currency"],
        "total_omr": order["total_baisa"] / 1000,
        "total_usd": catalog.baisa_to_usd(order["total_baisa"]),
        "email": order["email"],
        "created_at": order["created_at"],
        "items": [
            {
                "sku": it["sku"],
                "item_type": it["item_type"],
                "name": it["name"],
                "quantity": it["quantity"],
                "unit_price_omr": it["unit_price_baisa"] / 1000,
                "unit_price_usd": catalog.baisa_to_usd(it["unit_price_baisa"]),
                "line_total_omr": it["line_total_baisa"] / 1000,
                "line_total_usd": catalog.baisa_to_usd(it["line_total_baisa"]),
            }
            for it in items
        ],
    }


@router.post("/orders/checkout", status_code=201)
def checkout(body: CheckoutReq, user: dict | None = Depends(get_current_user)):
    if not config.THAWANI_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="Payment isn't connected yet (Thawani credentials not configured). Nothing was charged.",
        )

    line_items = []
    total_baisa = 0
    for item in body.items:
        product = catalog.CATALOG[item.sku]
        line_total = product.omr_baisa * item.quantity
        total_baisa += line_total
        line_items.append(
            {
                "sku": product.sku,
                "item_type": product.item_type,
                "name": product.name,
                "unit_price_baisa": product.omr_baisa,
                "quantity": item.quantity,
                "line_total_baisa": line_total,
            }
        )

    order_token = secrets.token_urlsafe(24)
    shipping = body.shipping_address.model_dump()

    with db.get_conn() as conn:
        with conn.transaction():
            order = conn.execute(
                """
                INSERT INTO orders (order_token, user_id, email, phone, shipping_address, status, currency, total_baisa)
                VALUES (%s, %s, %s, %s, %s, 'pending', 'OMR', %s)
                RETURNING *
                """,
                (order_token, user["id"] if user else None, body.email, body.phone, json.dumps(shipping), total_baisa),
            ).fetchone()
            for it in line_items:
                conn.execute(
                    """
                    INSERT INTO order_items (order_id, sku, item_type, name, unit_price_baisa, quantity, line_total_baisa)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (order["id"], it["sku"], it["item_type"], it["name"], it["unit_price_baisa"], it["quantity"], it["line_total_baisa"]),
                )

    callback_url = f"{config.PUBLIC_API_URL}/api/orders/callback?token={order_token}"
    try:
        session = thawani.create_session(
            client_reference_id=order_token,
            products=[{"name": it["name"], "unit_amount": it["unit_price_baisa"], "quantity": it["quantity"]} for it in line_items],
            success_url=callback_url,
            cancel_url=callback_url,
            metadata={"order_token": order_token, "email": body.email, "phone": body.phone},
        )
    except thawani.ThawaniError as exc:
        db.execute("UPDATE orders SET status = 'failed', updated_at = %s WHERE id = %s", (datetime.now(timezone.utc), order["id"]))
        logger.warning("orders: Thawani session creation failed for order_token=%s: %s", order_token, exc)
        raise HTTPException(status_code=502, detail="Could not start payment with Thawani. Please try again.") from exc

    db.execute(
        "UPDATE orders SET thawani_session_id = %s, updated_at = %s WHERE id = %s",
        (session["session_id"], datetime.now(timezone.utc), order["id"]),
    )
    logger.info("orders: created order_token=%s total_baisa=%s items=%s", order_token, total_baisa, [it["sku"] for it in line_items])
    return {"order_token": order_token, "checkout_url": session["checkout_url"]}


@router.get("/orders/callback")
def thawani_callback(token: str):
    """Thawani redirects the browser here after checkout (both success and
    cancel point at the same URL — see checkout() above). We never trust
    the mere fact of being redirected here; we re-verify with Thawani's own
    API using our secret key before marking anything paid."""
    order = db.fetch_one("SELECT * FROM orders WHERE order_token = %s", (token,))
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order["status"] == "pending" and order["thawani_session_id"]:
        try:
            payment_status = thawani.get_session_status(order["thawani_session_id"])
        except thawani.ThawaniError as exc:
            logger.warning("orders: callback status check failed for order_token=%s: %s", token, exc)
            payment_status = None

        new_status = {"paid": "paid", "cancelled": "cancelled"}.get(payment_status)
        if new_status:
            db.execute(
                "UPDATE orders SET status = %s, updated_at = %s WHERE id = %s",
                (new_status, datetime.now(timezone.utc), order["id"]),
            )
            logger.info("orders: order_token=%s -> %s (thawani payment_status=%s)", token, new_status, payment_status)

    return RedirectResponse(url=f"{config.PUBLIC_SITE_URL}/order/{token}", status_code=302)


@router.get("/orders/{token}")
def get_order(token: str):
    order = db.fetch_one("SELECT * FROM orders WHERE order_token = %s", (token,))
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    items = db.fetch_all("SELECT * FROM order_items WHERE order_id = %s ORDER BY id", (order["id"],))
    return _order_out(order, items)
