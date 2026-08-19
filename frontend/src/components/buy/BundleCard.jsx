import { Check, Droplets, Package, Plus, Star } from "lucide-react";
import { Tilt3DCard } from "./Tilt3DCard";
import { ProductImage } from "./ProductImage";
import { useLang } from "../../i18n/LanguageContext";

const IMAGE_BY_SKU = {
  STARTER: "/products/bundle-starter.png",
  VALUE: "/products/bundle-value.png",
  PRO: "/products/bundle-pro.png",
};

// One bundle in the §2b comparison grid. `recommended` visually marks the
// Value bundle (target mix in the financial model, best absolute margin) —
// no fake urgency/scarcity copy, just the real price/strip-count comparison.
export function BundleCard({ bundle, recommended, qtyInCart, onAdd }) {
  const { t } = useLang();
  const features = [
    `${bundle.strip_count} ${t("buy.bundles.strips")}`,
    t("buy.bundles.feature.sealed"),
    t("buy.bundles.feature.compatible"),
  ];

  return (
    <Tilt3DCard highlight={recommended} className="relative h-full">
      {recommended && (
        <span className="absolute -top-3 start-6 z-10 inline-flex items-center gap-1.5 rounded-full px-3 py-1 font-mono text-[10px] font-semibold uppercase tracking-wide text-white brand-gradient">
          <Star size={11} fill="currentColor" /> {t("buy.bundles.recommended")}
        </span>
      )}

      <ProductImage src={IMAGE_BY_SKU[bundle.sku]} alt={bundle.name} icon={Droplets} className="mb-5 h-40 w-full" />

      <h3 className="font-display text-xl font-semibold text-depth">{bundle.name}</h3>

      <ul className="mt-4 space-y-2">
        {features.map((f) => (
          <li key={f} className="flex items-start gap-2 text-sm text-depth/70">
            <Check size={15} className="mt-0.5 shrink-0 text-signal" /> {f}
          </li>
        ))}
      </ul>

      <div className="mt-6 flex items-baseline gap-2" dir="ltr">
        <span className="font-display text-3xl font-bold text-depth">${bundle.price_usd.toFixed(2)}</span>
        <span className="font-mono text-xs text-depth/45">({bundle.price_omr.toFixed(3)} OMR)</span>
      </div>
      <p className="mt-1 font-mono text-xs text-depth/50" dir="ltr">
        ${bundle.price_per_strip_usd.toFixed(2)} {t("buy.bundles.perStrip")}
      </p>

      <button
        type="button"
        onClick={() => onAdd(bundle.sku)}
        className={`mt-6 inline-flex items-center justify-center gap-2 rounded-full px-5 py-3 font-semibold transition duration-200 ease-expo active:scale-[0.98] ${
          recommended ? "btn-primary" : "btn-ghost !border-depth/15 !text-depth hover:!border-signal/50"
        }`}
      >
        {qtyInCart > 0 ? (
          <>
            <Package size={16} /> {t("buy.bundles.added")} ({qtyInCart})
          </>
        ) : (
          <>
            <Plus size={16} /> {t("buy.bundles.add")}
          </>
        )}
      </button>
    </Tilt3DCard>
  );
}
