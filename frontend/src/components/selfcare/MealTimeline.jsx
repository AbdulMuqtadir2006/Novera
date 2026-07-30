import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Sunrise, Sun, Cookie, Moon, Flame, Clock } from "lucide-react";
import { AnimatedNumber } from "../ui/AnimatedNumber";

// Meal windows across the day (24h). `at` is the centre used on the timeline.
const MEALS = [
  { id: "breakfast", icon: Sunrise, start: 6, end: 10, at: 8 },
  { id: "lunch", icon: Sun, start: 12, end: 15, at: 13.25 },
  { id: "snacks", icon: Cookie, start: 16, end: 18, at: 17 },
  { id: "dinner", icon: Moon, start: 19, end: 22.5, at: 20.5 },
];
const DAY_START = 6;
const DAY_END = 23.5;
const pct = (h) => Math.max(0, Math.min(100, ((h - DAY_START) / (DAY_END - DAY_START)) * 100));

const MACROS = [
  { key: "protein_g", label: "Protein", color: "#28CFE0", max: 45 },
  { key: "carbs_g", label: "Carbs", color: "#EC61E8", max: 95 },
  { key: "fat_g", label: "Fat", color: "#B24BD6", max: 40 },
];

function useNow() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 30000);
    return () => clearInterval(id);
  }, []);
  return now;
}

function fmtTime(h, lang) {
  const hh = Math.floor(h);
  const mm = Math.round((h - hh) * 60);
  const d = new Date();
  d.setHours(hh, mm, 0, 0);
  return d.toLocaleTimeString(lang === "ar" ? "ar" : undefined, { hour: "numeric", minute: "2-digit" });
}

function pickMeal(nowH) {
  const inside = MEALS.find((m) => nowH >= m.start && nowH < m.end);
  if (inside) return { meal: inside, mode: "now" };
  const upcoming = MEALS.find((m) => m.start > nowH);
  if (upcoming) return { meal: upcoming, mode: "next" };
  return { meal: MEALS[0], mode: "tomorrow" }; // after dinner -> tomorrow's breakfast
}

export function MealTimeline({ plan, t, lang }) {
  const now = useNow();
  const nowH = now.getHours() + now.getMinutes() / 60;
  const { meal, mode } = pickMeal(nowH);
  const Icon = meal.icon;

  const nutrition = (plan?.nutrition || []).reduce((acc, n) => ({ ...acc, [n.meal]: n }), {});
  const nut = nutrition[meal.id] || {};
  const food = plan?.dietPlan?.[meal.id] || "";

  const contextLabel =
    mode === "now"
      ? t("selfcare.nowEat")
      : mode === "next"
      ? `${t("selfcare.upNext")} · ${fmtTime(meal.at, lang)}`
      : `${t("selfcare.tomorrow")} · ${fmtTime(meal.at, lang)}`;

  return (
    <div className="light-card overflow-hidden p-6">
      <div className="mb-5 flex items-center justify-between">
        <h3 className="flex items-center gap-2 font-display text-lg font-bold text-depth">
          <Clock size={18} className="text-signal" /> {t("selfcare.yourDay")}
        </h3>
        <span className="font-mono text-sm text-depth/60">{fmtTime(nowH, lang)}</span>
      </div>

      {/* timeline track */}
      <div className="relative mx-1 mb-10 mt-8 h-1.5">
        <div className="absolute inset-0 rounded-full bg-depth/10" />
        {/* elapsed day */}
        <motion.div
          className="absolute inset-y-0 left-0 rounded-full brand-gradient"
          initial={{ width: 0 }}
          animate={{ width: `${pct(nowH)}%` }}
          transition={{ duration: 1, ease: [0.16, 1, 0.3, 1] }}
        />
        {/* meal markers */}
        {MEALS.map((m) => {
          const active = m.id === meal.id;
          const MIcon = m.icon;
          return (
            <div key={m.id} className="absolute -translate-x-1/2" style={{ left: `${pct(m.at)}%`, top: "-14px" }}>
              <motion.div
                className={`grid h-9 w-9 place-items-center rounded-full border transition-colors ${
                  active
                    ? "border-transparent brand-gradient text-white shadow-glow"
                    : "border-signal/25 bg-paper text-depth/50"
                }`}
                animate={active ? { scale: [1, 1.12, 1] } : { scale: 1 }}
                transition={active ? { duration: 1.8, repeat: Infinity, ease: "easeInOut" } : {}}
              >
                <MIcon size={17} />
              </motion.div>
              <span className={`mt-2 block whitespace-nowrap text-center text-[11px] font-medium ${active ? "text-depth" : "text-depth/45"}`}>
                {t(`selfcare.${m.id}`)}
              </span>
            </div>
          );
        })}
        {/* now marker */}
        <motion.div
          className="absolute top-1/2 z-10 -translate-x-1/2 -translate-y-1/2"
          initial={false}
          animate={{ left: `${pct(nowH)}%` }}
          transition={{ duration: 1, ease: [0.16, 1, 0.3, 1] }}
        >
          <span className="relative flex h-4 w-4">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-signal/60" />
            <span className="relative inline-flex h-4 w-4 rounded-full border-2 border-white bg-signal" />
          </span>
        </motion.div>
      </div>

      {/* current recommendation */}
      <motion.div
        key={meal.id}
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className="rounded-2xl border border-signal/15 bg-gradient-to-br from-mist/60 to-paper p-5"
      >
        <div className="flex items-start gap-4">
          <span className="grid h-12 w-12 shrink-0 place-items-center rounded-xl brand-gradient text-white shadow-glow-sm">
            <Icon size={24} />
          </span>
          <div className="min-w-0 flex-1">
            <p className="font-mono text-[11px] uppercase tracking-wide text-signal">{contextLabel}</p>
            <h4 className="font-display text-xl font-bold text-depth">{t(`selfcare.${meal.id}`)}</h4>
            <p className="mt-1 text-sm leading-relaxed text-depth/75">{food}</p>
          </div>
        </div>

        {/* macros */}
        <div className="mt-5 grid gap-5 sm:grid-cols-[auto_1fr] sm:items-center">
          {/* calories */}
          <div className="flex items-center gap-3">
            <span className="grid h-11 w-11 place-items-center rounded-full bg-vital/12 text-vital">
              <Flame size={20} />
            </span>
            <div>
              <p className="font-mono text-2xl font-bold tabular-nums text-depth">
                <AnimatedNumber value={nut.calories || 0} duration={900} />
              </p>
              <p className="-mt-1 text-xs text-depth/50">{t("selfcare.kcal")}</p>
            </div>
          </div>
          {/* macro bars */}
          <div className="space-y-2.5">
            {MACROS.map((mac) => {
              const val = nut[mac.key] || 0;
              return (
                <div key={mac.key} className="flex items-center gap-3">
                  <span className="w-14 shrink-0 text-xs font-medium text-depth/60">{t(`selfcare.macro_${mac.key}`)}</span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-depth/10">
                    <motion.div
                      className="h-full rounded-full"
                      style={{ backgroundColor: mac.color }}
                      initial={{ width: 0 }}
                      animate={{ width: `${Math.min(100, (val / mac.max) * 100)}%` }}
                      transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1], delay: 0.15 }}
                    />
                  </div>
                  <span className="w-10 shrink-0 text-end font-mono text-xs tabular-nums text-depth/70">{val}g</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* micros */}
        {nut.micros?.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {nut.micros.map((m, i) => (
              <span key={i} className="rounded-full bg-signal/10 px-2.5 py-1 text-xs font-medium text-depth/75">
                {m}
              </span>
            ))}
          </div>
        )}
      </motion.div>
    </div>
  );
}
