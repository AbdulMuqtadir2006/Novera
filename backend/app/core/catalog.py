"""NOVERA store catalog — device + strip bundles.

*** LOAD-BEARING, DO NOT EDIT SILENTLY ***
The four USD prices below are the actual numbers the NOVERA business/
financial model is built on (device COGS $95/margin $34; Starter bundle
COGS $15/margin $12 @ 44.4%; Value bundle COGS $37.5/margin $20.5 @ 35.3%;
Pro bundle COGS $75/margin $23 @ 23.5%). If a price ever needs to change,
flag it and update the business plan alongside this file — never edit only
here. This module is the SINGLE source of truth for pricing: the frontend
has no hardcoded prices of its own, it fetches GET /api/catalog, and
checkout always prices from here server-side, never from client input
(never trust a client-submitted price for what to charge).

Currency: OMR, converted from the USD figures above at the Central Bank of
Oman's official fixed peg (in place since 1986): 1 OMR = 2.6008 USD, i.e.
1 USD = 0.3845 OMR (https://cbo.gov.om/Pages/FixedPeg.aspx). This is a
hard currency peg, not a floating market rate — CBO actively defends it by
buying/selling OMR — so unlike most FX pairs there is no "staleness" risk
in hardcoding it; it has not moved since 1986 and is not expected to.
OMR's smallest unit is the baisa (1 OMR = 1,000 baisa) — Thawani's
checkout API requires unit_amount as an integer number of baisa, so every
OMR price here is pre-rounded to whole baisa.
"""
from __future__ import annotations

from dataclasses import dataclass, field

OMR_PER_USD = 0.3845  # see module docstring — CBO fixed peg, not a floating rate


def _omr_baisa(usd: float) -> int:
    return round(usd * OMR_PER_USD * 1000)


def baisa_to_usd(baisa: int) -> float:
    """Reverse of the above — used to show a USD-equivalent figure for
    amounts already charged in OMR (e.g. a past order), display-only."""
    return round((baisa / 1000) / OMR_PER_USD, 2)


@dataclass(frozen=True)
class Product:
    sku: str
    item_type: str  # "device" | "bundle" — kept as separate cart/order line items, never collapsed (see routers/orders.py)
    name: str
    usd_price: float  # the load-bearing business-model figure — see module docstring
    strip_count: int | None  # None for the device itself
    omr_baisa: int = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, "omr_baisa", _omr_baisa(self.usd_price))

    @property
    def omr_price(self) -> float:
        return self.omr_baisa / 1000

    @property
    def price_per_strip_omr(self) -> float | None:
        if not self.strip_count:
            return None
        return round(self.omr_baisa / self.strip_count) / 1000


DEVICE = Product(sku="DEVICE", item_type="device", name="NOVERA Reader", usd_price=129, strip_count=None)
STARTER = Product(sku="STARTER", item_type="bundle", name="Starter Bundle", usd_price=27, strip_count=10)
VALUE = Product(sku="VALUE", item_type="bundle", name="Value Bundle", usd_price=58, strip_count=25)
PRO = Product(sku="PRO", item_type="bundle", name="Pro Bundle", usd_price=98, strip_count=50)

CATALOG: dict[str, Product] = {p.sku: p for p in (DEVICE, STARTER, VALUE, PRO)}
BUNDLE_SKUS = ("STARTER", "VALUE", "PRO")

# Value is the target mix in the financial model (44% of bundle sales) and
# has the best absolute margin ($20.5) — surfaced to the storefront as the
# recommended bundle, not just a UX nicety. Change this if the model's
# target mix changes, not independently of it.
RECOMMENDED_SKU = "VALUE"


def public_catalog() -> dict:
    """Customer-facing shape for GET /api/catalog — price/contents only,
    never COGS/margin (that's internal financial-model data, not for the
    storefront). USD is the display-primary currency (per Hassan,
    2026-08-20) with the OMR conversion shown small alongside it — but
    OMR/baisa is still what actually gets charged via Thawani (Thawani only
    accepts OMR); `currency` stays "OMR" since that's what a completed
    checkout is denominated in, USD here is display-only."""
    return {
        "currency": "OMR",
        "display_currency": "USD",
        "device": _public_product(DEVICE),
        "bundles": [_public_product(CATALOG[sku]) for sku in BUNDLE_SKUS],
        "recommended_sku": RECOMMENDED_SKU,
    }


def _public_product(p: Product) -> dict:
    return {
        "sku": p.sku,
        "item_type": p.item_type,
        "name": p.name,
        "strip_count": p.strip_count,
        "price_usd": p.usd_price,
        "price_omr": p.omr_price,
        "price_per_strip_usd": round(p.usd_price / p.strip_count, 3) if p.strip_count else None,
        "price_per_strip_omr": p.price_per_strip_omr,
    }
