import { motion } from "framer-motion";
import { statusMeta } from "../../lib/format";
import { useLang } from "../../i18n/LanguageContext";

const SCORE = { good: 1, watch: 0.6, attention: 0.25 };
const RANK = { good: 0, watch: 1, attention: 2 };

export function ScreeningGauge({ healthAreas }) {
  const { t, lang } = useLang();
  const entries = Object.entries(healthAreas);
  const avg =
    entries.reduce((s, [, st]) => s + SCORE[st], 0) / (entries.length || 1);

  // Overall state = the worst area (most conservative).
  const overall = entries.reduce(
    (worst, [, st]) => (RANK[st] > RANK[worst] ? st : worst),
    "good"
  );
  const meta = statusMeta[overall];

  const R = 78;
  const C = 2 * Math.PI * R;
  const offset = C * (1 - avg);

  const OVERALL = {
    en: { good: "Looking steady", watch: "A couple to watch", attention: "Worth a closer look" },
    ar: { good: "تبدو مستقرة", watch: "اثنان يستحقان المتابعة", attention: "تستحق نظرة أقرب" },
  };
  const overallLabel = (OVERALL[lang] || OVERALL.en)[overall];

  return (
    <div className="light-card flex flex-col items-center gap-6 p-6 sm:flex-row sm:items-center sm:gap-8">
      <div className="relative flex h-48 w-48 shrink-0 items-center justify-center">
        <svg viewBox="0 0 180 180" className="h-full w-full -rotate-90">
          <circle cx="90" cy="90" r={R} fill="none" stroke="#241A44" strokeOpacity="0.1" strokeWidth="12" />
          <motion.circle
            cx="90"
            cy="90"
            r={R}
            fill="none"
            stroke={meta.color}
            strokeWidth="12"
            strokeLinecap="round"
            strokeDasharray={C}
            initial={{ strokeDashoffset: C }}
            animate={{ strokeDashoffset: offset }}
            transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
          />
        </svg>
        <div className="absolute flex flex-col items-center">
          <span className="font-mono text-3xl font-semibold tabular-nums text-depth">
            {Math.round(avg * 100)}
          </span>
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-depth/45">
            {t("dash.index")}
          </span>
        </div>
      </div>

      <div className="flex-1">
        <p className="eyebrow text-depth/60">{t("dash.screening")}</p>
        <p className="mt-2 font-display text-2xl font-bold" style={{ color: meta.color }}>
          {overallLabel}
        </p>

        <div className="mt-5 grid grid-cols-2 gap-3">
          {entries.map(([id, st]) => {
            const c = statusMeta[st].color;
            return (
              <div key={id} className="flex items-center gap-2.5">
                <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: c }} />
                <span className="text-sm text-depth/75">{t(`area.${id}`)}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
