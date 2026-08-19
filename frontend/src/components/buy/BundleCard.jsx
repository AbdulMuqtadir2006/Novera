import { motion } from "framer-motion";
import { Check, Plus, Star } from "lucide-react";
import { staggerItem } from "../ui/Reveal";
import { useLang } from "../../i18n/LanguageContext";

// One bundle in the §2b comparison grid. `recommended` visually marks the
// Value bundle (target mix in the financial model, best absolute margin) —
// no fake urgency/scarcity copy, just the real price/strip-count comparison.
export function BundleCard({ bundle, recommended, qtyInCart, onAdd }) {
  const { t } = useLang();
  return (
    <motion.div variants={staggerItem} className="relative h-full">
      <div
        className={`glass-card relative flex h-full flex-col p-7 transition-colors duration-300 ${
          recommended ? "border-vital/50 shadow-glow-magenta" : "hover:border-signal/40"
        }`}
      >
        {recommended && (
          <span className="absolute -top-3 start-6 inline-flex items-center gap-1.5 rounded-full px-3 py-1 font-mono text-[10px] font-semibold uppercase tracking-wide text-white brand-gradient">
            <Star size={11} fill="currentColor" /> {t("buy.bundles.recommended")}
          </span>
        )}

        <h3 className="font-display text-xl font-semibold text-white">{bundle.name}</h3>
        <p className="mt-1 text-sm text-slate-400">
          {bundle.strip_count} {t("buy.bundles.strips")}
        </p>

        <div className="mt-6 flex items-baseline gap-2" dir="ltr">
          <span className="font-display text-3xl font-bold text-white">{bundle.price_omr.toFixed(3)}</span>
          <span className="font-mono text-sm text-slate-400">OMR</span>
        </div>
        <p className="mt-1 font-mono text-xs text-slate-500" dir="ltr">
          {bundle.price_per_strip_omr.toFixed(3)} OMR {t("buy.bundles.perStrip")}
        </p>

        <button
          type="button"
          onClick={() => onAdd(bundle.sku)}
          className={`mt-7 inline-flex items-center justify-center gap-2 rounded-full px-5 py-3 font-semibold transition duration-200 ease-expo active:scale-[0.98] ${
            recommended ? "btn-primary" : "btn-ghost"
          }`}
        >
          {qtyInCart > 0 ? (
            <>
              <Check size={16} /> {t("buy.bundles.added")} ({qtyInCart})
            </>
          ) : (
            <>
              <Plus size={16} /> {t("buy.bundles.add")}
            </>
          )}
        </button>
      </div>
    </motion.div>
  );
}
