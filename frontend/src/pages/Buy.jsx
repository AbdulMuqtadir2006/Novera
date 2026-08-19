import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowRight, Minus, Plus, ShieldAlert, Trash2, Zap } from "lucide-react";
import { Section } from "../components/home/Section";
import { BundleCard } from "../components/buy/BundleCard";
import { CheckoutForm } from "../components/buy/CheckoutForm";
import { staggerContainer } from "../components/ui/Reveal";
import { getCatalog, checkout as checkoutApi } from "../lib/api";
import { useLang } from "../i18n/LanguageContext";

// NOVERA store — device + strip bundles. One-time purchases only: no
// subscription, no referral/hospital-booking content (that belongs to a
// post-purchase results flow if it's ever built, not here).
//
// `?mode=strips` is the §2c "already have a reader" entry point — same
// page/route (not a separate one), just skips the device section/copy and
// jumps straight to the bundle comparison, per spec. A distinct button on
// the device view links here; a link back the other way is also offered.
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
  // and bundle line items are tracked separately either way (see
  // routers/orders.py — item_type per line, never collapsed into one SKU).
  const cartItems = useMemo(() => {
    if (!catalog) return [];
    const all = [catalog.device, ...catalog.bundles];
    return Object.entries(cart)
      .map(([sku, qty]) => ({ product: all.find((p) => p.sku === sku), qty }))
      .filter((it) => it.product && it.qty > 0);
  }, [cart, catalog]);

  const total = cartItems.reduce((sum, it) => sum + it.product.price_omr * it.qty, 0);

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

  if (loadError) {
    return (
      <main className="relative bg-ink py-32 text-center text-slate-300">
        <p>{t("buy.loadError")}</p>
      </main>
    );
  }

  return (
    <motion.main
      className="relative min-h-screen bg-ink"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.3 }}
    >
      <div className="pointer-events-none absolute inset-0 grid-lines opacity-30" aria-hidden="true" />

      <Section
        id="buy"
        eyebrow={t("buy.eyebrow")}
        title={stripsOnly ? t("buy.stripsOnly.title") : t("buy.device.title")}
        intro={stripsOnly ? t("buy.stripsOnly.body") : t("buy.device.tagline")}
        className="pt-32 sm:pt-40"
      >
        {/* §5 — visible near the price, not buried in a footer/terms link */}
        <div className="mb-10 flex items-start gap-3 rounded-2xl border border-vital/25 bg-vital/[0.06] p-4 text-sm text-slate-300">
          <ShieldAlert size={18} className="mt-0.5 shrink-0 text-vital" />
          <p>{t("buy.disclaimer")}</p>
        </div>

        <div className="grid gap-10 lg:grid-cols-[1.5fr_1fr] lg:items-start">
          <div>
            {!stripsOnly && (
              <div className="glass-card p-7">
                <span className="flex h-14 w-14 items-center justify-center rounded-2xl border border-signal/20 bg-signal/5 text-signal">
                  <Zap size={26} strokeWidth={1.75} />
                </span>
                <p className="mt-5 max-w-xl text-sm leading-relaxed text-slate-400">{t("buy.device.body")}</p>

                {catalog && (
                  <div className="mt-6 flex items-baseline gap-2" dir="ltr">
                    <span className="font-display text-4xl font-bold text-white">
                      {catalog.device.price_omr.toFixed(3)}
                    </span>
                    <span className="font-mono text-sm text-slate-400">OMR</span>
                  </div>
                )}
                <p className="mt-1 text-xs text-slate-500">{t("buy.device.priceNote")}</p>

                <button
                  type="button"
                  onClick={() => addItem("DEVICE")}
                  className="btn-primary mt-6 inline-flex items-center gap-2"
                >
                  {t("buy.device.cta")} <ArrowRight size={16} />
                </button>

                <button
                  type="button"
                  onClick={() => setSearchParams({ mode: "strips" })}
                  className="mt-4 block text-sm font-medium text-signal underline decoration-signal/40 underline-offset-4 hover:decoration-signal"
                >
                  {t("buy.stripsOnly.title")} {t("buy.stripsOnly.cta")} →
                </button>
              </div>
            )}

            {stripsOnly && (
              <button
                type="button"
                onClick={() => setSearchParams({})}
                className="mb-2 inline-flex items-center gap-1.5 text-sm font-medium text-signal underline decoration-signal/40 underline-offset-4 hover:decoration-signal"
              >
                {t("buy.backToDevice")} {t("buy.backToDeviceCta")} →
              </button>
            )}

            <div className="mt-10">
              <p className="eyebrow mb-2">{t("buy.bundles.eyebrow")}</p>
              <h2 className="font-display text-2xl font-bold text-white">{t("buy.bundles.title")}</h2>
              <p className="mt-2 max-w-xl text-sm leading-relaxed text-slate-400">{t("buy.bundles.intro")}</p>

              {!catalog ? (
                <p className="mt-8 text-sm text-slate-400">{t("buy.loading")}</p>
              ) : (
                <motion.div
                  className="mt-8 grid gap-6 sm:grid-cols-3"
                  variants={staggerContainer}
                  initial="hidden"
                  whileInView="show"
                  viewport={{ once: true, margin: "0px 0px -10% 0px" }}
                >
                  {catalog.bundles.map((bundle) => (
                    <BundleCard
                      key={bundle.sku}
                      bundle={bundle}
                      recommended={bundle.sku === catalog.recommended_sku}
                      qtyInCart={cart[bundle.sku] || 0}
                      onAdd={addItem}
                    />
                  ))}
                </motion.div>
              )}
            </div>
          </div>

          {/* Cart + checkout sidebar */}
          <div className="glass-card p-6 lg:sticky lg:top-24">
            <h3 className="font-display text-lg font-semibold text-white">{t("buy.cart.title")}</h3>

            {cartItems.length === 0 ? (
              <p className="mt-4 text-sm text-slate-400">{t("buy.cart.empty")}</p>
            ) : (
              <ul className="mt-4 space-y-3">
                {cartItems.map(({ product, qty }) => (
                  <li key={product.sku} className="flex items-center justify-between gap-3 border-b border-white/10 pb-3">
                    <div>
                      <p className="text-sm font-medium text-white">
                        {product.sku === "DEVICE" ? t("buy.cart.device") : product.name}
                      </p>
                      <p className="font-mono text-xs text-slate-500" dir="ltr">
                        {product.price_omr.toFixed(3)} OMR
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        aria-label={t("buy.cart.remove")}
                        onClick={() => setQty(product.sku, qty - 1)}
                        className="flex h-7 w-7 items-center justify-center rounded-full border border-white/15 text-slate-300 hover:border-signal/50 hover:text-white"
                      >
                        <Minus size={13} />
                      </button>
                      <span className="w-5 text-center font-mono text-sm text-white">{qty}</span>
                      <button
                        type="button"
                        aria-label={t("buy.bundles.add")}
                        onClick={() => setQty(product.sku, qty + 1)}
                        className="flex h-7 w-7 items-center justify-center rounded-full border border-white/15 text-slate-300 hover:border-signal/50 hover:text-white"
                      >
                        <Plus size={13} />
                      </button>
                      <button
                        type="button"
                        aria-label={t("buy.cart.remove")}
                        onClick={() => setQty(product.sku, 0)}
                        className="flex h-7 w-7 items-center justify-center rounded-full text-slate-500 hover:text-status-attention"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}

            {cartItems.length > 0 && (
              <>
                <div className="mt-4 flex items-baseline justify-between">
                  <span className="text-sm font-medium text-slate-300">{t("buy.cart.total")}</span>
                  <span className="font-display text-xl font-bold text-white" dir="ltr">
                    {total.toFixed(3)} OMR
                  </span>
                </div>
                <CheckoutForm onSubmit={handleCheckout} submitting={submitting} error={checkoutError} />
              </>
            )}
          </div>
        </div>
      </Section>
    </motion.main>
  );
}
