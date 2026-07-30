import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Plus, Loader2 } from "lucide-react";
import { PageShell } from "../components/layout/PageShell";
import { ReadingCard } from "../components/dashboard/ReadingCard";
import { TrendChart } from "../components/dashboard/TrendChart";
import { ScreeningGauge } from "../components/dashboard/ScreeningGauge";
import { StatusBadge } from "../components/dashboard/StatusBadge";
import { useLatestReading, useReadingHistory } from "../hooks/useLatestReading";
import { addReading } from "../lib/api";
import { AnimatedNumber } from "../components/ui/AnimatedNumber";
import { staggerContainer } from "../components/ui/Reveal";
import { useLang } from "../i18n/LanguageContext";

const METRIC_KEYS = ["ph", "creatinine", "urea", "temperature"];

function fmtTime(iso, lang) {
  return new Date(iso).toLocaleString(lang === "ar" ? "ar" : undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
function fmtDate(iso, lang) {
  return new Date(iso).toLocaleDateString(lang === "ar" ? "ar" : undefined, {
    month: "short",
    day: "numeric",
  });
}

function RangeToggle({ value, onChange }) {
  const { t } = useLang();
  const RANGES = [
    { id: 7, label: t("dash.range7") },
    { id: 30, label: t("dash.range30") },
    { id: 9999, label: t("dash.rangeAll") },
  ];
  return (
    <div role="tablist" aria-label="range" className="inline-flex rounded-full border border-signal/20 bg-paper p-1">
      {RANGES.map((r) => {
        const active = value === r.id;
        return (
          <button
            key={r.id}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(r.id)}
            className="relative rounded-full px-4 py-1.5 text-sm font-medium text-depth/70 transition-colors duration-200 hover:text-depth"
          >
            {active && (
              <motion.span
                layoutId="range-pill"
                className="absolute inset-0 -z-10 rounded-full bg-signal/15"
                transition={{ type: "spring", stiffness: 360, damping: 30 }}
              />
            )}
            <span className={active ? "text-depth" : ""}>{r.label}</span>
          </button>
        );
      })}
    </div>
  );
}

function SkeletonGrid() {
  return (
    <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="light-card h-40 animate-pulse p-5">
          <div className="h-3 w-16 rounded bg-depth/10" />
          <div className="mt-4 h-8 w-24 rounded bg-depth/10" />
          <div className="mt-6 h-10 w-full rounded bg-depth/5" />
        </div>
      ))}
    </div>
  );
}

// Prominent banner for the single most-recently-entered reading.
function LatestValueHero({ reading, lang }) {
  const { t } = useLang();
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      className="relative overflow-hidden rounded-3xl bg-depth p-6 text-white sm:p-8"
    >
      <div className="pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full bg-signal/20 blur-3xl" aria-hidden="true" />
      <div className="relative flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="flex items-center gap-2 font-mono text-xs uppercase tracking-[0.2em] text-signal">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-signal/60" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-signal" />
            </span>
            {t("dash.latestValue")}
          </p>
          <p className="mt-2 font-mono text-sm text-white/60">{fmtTime(reading.timestamp, lang)}</p>
        </div>
        <div className="grid grid-cols-2 gap-x-8 gap-y-4 sm:grid-cols-4">
          {METRIC_KEYS.map((key) => {
            const m = reading.metrics[key];
            return (
              <div key={key}>
                <p className="font-mono text-[11px] uppercase tracking-wide text-white/50">{t(`metric.${key}`)}</p>
                <p className="mt-1 flex items-baseline gap-1 font-mono text-2xl font-semibold tabular-nums">
                  <AnimatedNumber
                    value={m.value}
                    decimals={key === "urea" || key === "temperature" ? 1 : 2}
                    duration={900}
                  />
                  {m.unit && <span className="text-xs text-white/50">{m.unit}</span>}
                </p>
                <div className="mt-1"><StatusBadge status={m.status} pulse={false} /></div>
              </div>
            );
          })}
        </div>
      </div>
    </motion.div>
  );
}

export default function Dashboard() {
  const { t, lang } = useLang();
  const [refresh, setRefresh] = useState(0);
  const [days, setDays] = useState(30);
  const [adding, setAdding] = useState(false);
  const { reading, loading } = useLatestReading(refresh);
  const { history } = useReadingHistory(days === 9999 ? 30 : days, refresh);

  const trends = useMemo(() => {
    const out = {};
    for (const key of METRIC_KEYS) {
      out[key] = history.map((r) => ({
        date: fmtDate(r.timestamp, lang),
        value: r.metrics[key].value,
      }));
    }
    return out;
  }, [history, lang]);

  const handleAdd = async () => {
    setAdding(true);
    try {
      await addReading();
      setRefresh((n) => n + 1);
    } finally {
      setAdding(false);
    }
  };

  return (
    <PageShell wide>
      <header className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="eyebrow mb-2">{t("dash.eyebrow")}</p>
          <h1 className="font-display text-3xl font-bold text-depth sm:text-4xl">{t("dash.title")}</h1>
        </div>
        <button type="button" onClick={handleAdd} disabled={adding} className="btn-primary self-start disabled:opacity-60 sm:self-auto">
          {adding ? <Loader2 size={18} className="animate-spin" /> : <Plus size={18} />}
          {adding ? t("dash.adding") : t("dash.addReading")}
        </button>
      </header>

      {loading || !reading ? (
        <SkeletonGrid />
      ) : (
        <>
          <div className="mb-6">
            <LatestValueHero reading={reading} lang={lang} />
          </div>

          <motion.div
            className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4"
            variants={staggerContainer}
            initial="hidden"
            animate="show"
            key={refresh}
          >
            {METRIC_KEYS.map((key) => (
              <ReadingCard
                key={key}
                metricKey={key}
                metric={reading.metrics[key]}
                trend={(trends[key] ?? []).map((d) => d.value)}
              />
            ))}
          </motion.div>

          <div className="mt-6">
            <ScreeningGauge healthAreas={reading.healthAreas} />
          </div>

          <div className="mt-12 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <h2 className="font-display text-xl font-bold text-depth">{t("dash.trends")}</h2>
            <RangeToggle value={days} onChange={setDays} />
          </div>

          <div className="mt-6 grid gap-5 lg:grid-cols-2">
            {METRIC_KEYS.map((key) => (
              <TrendChart
                key={key}
                metricKey={key}
                data={trends[key] ?? []}
                range={reading.metrics[key].range}
                unit={reading.metrics[key].unit}
                status={reading.metrics[key].status}
              />
            ))}
          </div>
        </>
      )}
    </PageShell>
  );
}
