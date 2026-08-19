import { ArrowRight, Check, Radio, Zap } from "lucide-react";
import { Tilt3DCard } from "./Tilt3DCard";
import { ProductImage } from "./ProductImage";
import { useLang } from "../../i18n/LanguageContext";

// The NOVERA Reader — §2a, the "get started" entry point. Same 3D-tilt
// card treatment as the bundles below it, just larger and photo-led.
export function DeviceCard({ device, onAdd, onSwitchToStrips }) {
  const { t } = useLang();
  const features = [
    t("buy.device.feature.biomarkers"),
    t("buy.device.feature.wireless"),
    t("buy.device.feature.dashboard"),
    t("buy.device.feature.reusable"),
  ];

  return (
    <Tilt3DCard className="h-full">
      <div className="grid gap-6 sm:grid-cols-[minmax(0,220px)_1fr]">
        <ProductImage src="/products/novera-reader.png" alt={device.name} icon={Zap} className="h-48 w-full rounded-2xl sm:h-full" />

        <div className="flex flex-col">
          <span className="inline-flex w-fit items-center gap-1.5 rounded-full bg-signal/10 px-2.5 py-1 font-mono text-[10px] uppercase tracking-wide text-signal">
            <Radio size={11} /> {t("buy.eyebrow")}
          </span>
          <h2 className="mt-3 font-display text-2xl font-bold text-depth">{device.name}</h2>
          <p className="mt-2 text-sm leading-relaxed text-depth/65">{t("buy.device.body")}</p>

          <ul className="mt-4 grid gap-2 sm:grid-cols-2">
            {features.map((f) => (
              <li key={f} className="flex items-start gap-2 text-sm text-depth/70">
                <Check size={15} className="mt-0.5 shrink-0 text-signal" /> {f}
              </li>
            ))}
          </ul>

          <div className="mt-6 flex flex-wrap items-end justify-between gap-4">
            <div>
              <div className="flex items-baseline gap-2" dir="ltr">
                <span className="font-display text-4xl font-bold text-depth">${device.price_usd.toFixed(2)}</span>
                <span className="font-mono text-xs text-depth/45">({device.price_omr.toFixed(3)} OMR)</span>
              </div>
              <p className="mt-1 text-xs text-depth/50">{t("buy.device.priceNote")}</p>
            </div>
            <button type="button" onClick={() => onAdd("DEVICE")} className="btn-primary inline-flex items-center gap-2">
              {t("buy.device.cta")} <ArrowRight size={16} />
            </button>
          </div>

          <button
            type="button"
            onClick={onSwitchToStrips}
            className="mt-4 self-start text-sm font-medium text-signal underline decoration-signal/40 underline-offset-4 hover:decoration-signal"
          >
            {t("buy.stripsOnly.title")} {t("buy.stripsOnly.cta")} →
          </button>
        </div>
      </div>
    </Tilt3DCard>
  );
}
