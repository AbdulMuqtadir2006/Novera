import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import { Loader2, Minus, Plus, ShieldAlert, ShoppingCart, Trash2 } from "lucide-react";
import { PageShell } from "../components/layout/PageShell";
import { DeviceCard } from "../components/buy/DeviceCard";
import { BundleCard } from "../components/buy/BundleCard";
import { CheckoutForm } from "../components/buy/CheckoutForm";
import { Tilt3DCard } from "../components/buy/Tilt3DCard";
import { staggerContainer, staggerItem } from "../components/ui/Reveal";
import { getCatalog, checkout as checkoutApi } from "../lib/api";
import { useLang } from "../i18n/LanguageContext";

// NOVERA store — device + strip bundles. One-time purchases only: no
// subscription, no referral/hospital-booking content (that belongs to a
// post-purchase results flow if it's ever built, not here). Same light
// PageShell theme every other nav page (Dashboard/Reports/Self-Care) uses.
//
// `?mode=strips` is the §2c "already have a reader" entry point — same
// page/route (not a separate one), just skips the device card and jumps
// straight to the bundle comparison, per spec. A distinct button on the
// device view links here; a link back the other way is also offered.
export default function Buy() {
  const { t } = useLang();
  const [searchParams, setSearchParams] = useSearchParams();
  const stripsOnly = searchParams.get("mode") === "strips";

  const [catalog, setCatalog] = useState(null);
  const [loadError, setLoadError] = useState(false);
  const [cart, setCart] = useState({}); // sku -> qty
  const [submitting, setSubmitting] = useState(false);
  const [checkoutError, setCheckoutError] = useState("");

  useEffect(() => {
    getCatalog()
      .then(setCatalog)
      .catch(() => setLoadError(true));
  }, []);

  const addItem = (sku) => setCart((c) => ({ ...c, [sku]: (c[sku] || 0) + 1 }));
  const setQty = (sku, qty) =>
    setCart((c) => {
      if (qty <= 0) {
        const next = { ...c };
        delete next[sku];
        return next;
      }
      return { ...c, [sku]: qty };
    });

  // Decision: strips aren't auto-bundled into the device purchase — the
  // device and every bundle are separate "add to order" actions that share
  // one cart. This keeps the cart flow simple (one mechanism for every
  // product) and doesn't change the revenue math either way, since device
  // and bundle line items are tracked separately regardless (see
  // routers/orders.py — item_type per line, never collapsed into one SKU).
  const cartItems = useMemo(() => {
    if (!catalog) return [];
    const all = [catalog.device, ...catalog.bundles];
    return Object.entries(cart)
      .map(([sku, qty]) => ({ product: all.find((p) => p.sku === sku), qty }))
      .filter((it) => it.product && it.qty > 0);
  }, [cart, catalog]);

  const total = cartItems.reduce((sum, it) => sum + it.product.price_omr * it.qty, 0);
  const totalUsd = cartItems.reduce((sum, it) => sum + it.product.price_usd * it.qty, 0);

  const handleCheckout = async (contact) => {
    setSubmitting(true);
    setCheckoutError("");
    try {
      const { checkout_url } = await checkoutApi({
        ...contact,
        items: cartItems.map((it) => ({ sku: it.product.sku, quantity: it.qty })),
      });
      window.location.href = checkout_url;
    } catch (e) {
      setCheckoutError(e.status === 503 ? t("buy.checkout.gatewayOffline") : t("buy.checkout.error"));
      setSubmitting(false);
    }
  };

  return (
    <PageShell
      eyebrow={t("buy.eyebrow")}
      title={stripsOnly ? t("buy.stripsOnly.title") : t("buy.device.title")}
      intro={stripsOnly ? t("buy.stripsOnly.body") : t("buy.device.tagline")}
      wide
    >
      {/* §5 — visible near the price, not buried in a footer/terms link */}
      <div className="light-card mb-8 flex items-start gap-3 border-vital/25 bg-vital/[0.05] p-4 text-sm text-depth/75">
        <ShieldAlert size={18} className="mt-0.5 shrink-0 text-vital" />
        <p>{t("buy.disclaimer")}</p>
      </div>

      {loadError ? (
        <p className="text-depth/60">{t("buy.loadError")}</p>
      ) : (
        <div className="grid gap-8 lg:grid-cols-[1.6fr_1fr] lg:items-start">
          <div className="space-y-10">
            {!catalog ? (
              <div className="light-card flex h-56 items-center justify-center text-depth/50">
                <Loader2 size={22} className="animate-spin" />
              </div>
            ) : (
              <>
                {!stripsOnly && (
                  <DeviceCard device={catalog.device} onAdd={addItem} onSwitchToStrips={() => setSearchParams({ mode: "strips" })} />
                )}
                {stripsOnly && (
                  <button
                    type="button"
                    onClick={() => setSearchParams({})}
                    className="inline-flex items-center gap-1.5 text-sm font-medium text-signal underline decoration-signal/40 underline-offset-4 hover:decoration-signal"
                  >
                    {t("buy.backToDevice")} {t("buy.backToDeviceCta")} →
                  </button>
                )}

                <div>
                  <p className="eyebrow mb-2">{t("buy.bundles.eyebrow")}</p>
                  <h2 className="font-display text-2xl font-bold text-depth">{t("buy.bundles.title")}</h2>
                  <p className="mt-2 max-w-xl text-sm leading-relaxed text-depth/65">{t("buy.bundles.intro")}</p>

                  <motion.div
                    className="mt-7 grid gap-6 sm:grid-cols-3"
                    variants={staggerContainer}
                    initial="hidden"
                    whileInView="show"
                    viewport={{ once: true, margin: "0px 0px -10% 0px" }}
                  >
                    {catalog.bundles.map((bundle) => (
                      <motion.div key={bundle.sku} variants={staggerItem} className="h-full">
                        <BundleCard
                          bundle={bundle}
                          recommended={bundle.sku === catalog.recommended_sku}
                          qtyInCart={cart[bundle.sku] || 0}
                          onAdd={addItem}
                        />
                      </motion.div>
                    ))}
                  </motion.div>
                </div>
              </>
            )}
          </div>

          {/* Cart + checkout sidebar — always the same 3D card, whether it's
              empty (a non-interactive placeholder — nothing to click until
              something's added) or has items (fillable checkout form). */}
          <div className="lg:sticky lg:top-24">
            <Tilt3DCard>
              <h3 className="flex items-center gap-2 font-display text-lg font-semibold text-depth">
                <ShoppingCart size={18} className="text-signal" /> {t("buy.cart.title")}
              </h3>

              {cartItems.length === 0 ? (
                <div className="flex flex-1 flex-col items-center justify-center gap-3 py-10 text-center">
                  <span className="flex h-14 w-14 items-center justify-center rounded-full bg-signal/10 text-signal/60">
                    <ShoppingCart size={26} strokeWidth={1.5} />
                  </span>
                  <p className="max-w-[16rem] text-sm text-depth/50">{t("buy.cart.empty")}</p>
                </div>
              ) : (
                <>
                  <ul className="mt-4 space-y-3">
                    {cartItems.map(({ product, qty }) => (
                      <li key={product.sku} className="flex items-center justify-between gap-3 border-b border-depth/10 pb-3">
                        <div>
                          <p className="text-sm font-medium text-depth">
                            {product.sku === "DEVICE" ? t("buy.cart.device") : product.name}
                          </p>
                          <p className="font-mono text-xs text-depth/45" dir="ltr">
                            ${product.price_usd.toFixed(2)} <span className="text-depth/30">({product.price_omr.toFixed(3)} OMR)</span>
                          </p>
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            aria-label={t("buy.cart.remove")}
                            onClick={() => setQty(product.sku, qty - 1)}
                            className="flex h-7 w-7 items-center justify-center rounded-full border border-depth/15 text-depth/60 hover:border-signal/50 hover:text-depth"
                          >
                            <Minus size={13} />
                          </button>
                          <span className="w-5 text-center font-mono text-sm text-depth">{qty}</span>
                          <button
                            type="button"
                            aria-label={t("buy.bundles.add")}
                            onClick={() => setQty(product.sku, qty + 1)}
                            className="flex h-7 w-7 items-center justify-center rounded-full border border-depth/15 text-depth/60 hover:border-signal/50 hover:text-depth"
                          >
                            <Plus size={13} />
                          </button>
                          <button
                            type="button"
                            aria-label={t("buy.cart.remove")}
                            onClick={() => setQty(product.sku, 0)}
                            className="flex h-7 w-7 items-center justify-center rounded-full text-depth/35 hover:text-status-attention"
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>

                  <div className="mt-4 flex items-baseline justify-between">
                    <span className="text-sm font-medium text-depth/70">{t("buy.cart.total")}</span>
                    <span className="font-display text-xl font-bold text-depth" dir="ltr">
                      ${totalUsd.toFixed(2)}{" "}
                      <span className="font-mono text-xs font-normal text-depth/40">({total.toFixed(3)} OMR)</span>
                    </span>
                  </div>
                  <CheckoutForm onSubmit={handleCheckout} submitting={submitting} error={checkoutError} />
                </>
              )}
            </Tilt3DCard>
          </div>
        </div>
      )}
    </PageShell>
  );
}
