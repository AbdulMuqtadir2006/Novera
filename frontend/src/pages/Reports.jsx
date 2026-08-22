import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Download, Check, CircleAlert, Loader2, RefreshCw, Sparkles, Droplet } from "lucide-react";
import { PageShell } from "../components/layout/PageShell";
import { useLatestReading } from "../hooks/useLatestReading";
import { getReport } from "../lib/api";
import { generateReportPdf } from "../components/reports/generateReportPdf";
import { metricMeta, statusMeta, formatValue } from "../lib/format";
import { useLang } from "../i18n/LanguageContext";
import { Wordmark } from "../components/ui/Wordmark";
import { AgentThinking } from "../components/ui/AgentThinking";

const METRIC_KEYS = ["ph", "creatinine", "urea", "temperature"];

// The printable document — snapshotted to PDF and shown on screen.
function PrintableReport({ reading, report, lang, t, docRef }) {
  return (
    <div
      ref={docRef}
      dir={lang === "ar" ? "rtl" : "ltr"}
      className="rounded-2xl border border-signal/15 bg-white p-8 text-depth"
      style={{ fontFamily: lang === "ar" ? "Cairo, sans-serif" : undefined }}
    >
      <div className="flex items-center justify-between border-b border-signal/20 pb-4">
        <Wordmark tone="dark" />
        <div className="text-end">
          <p className="font-semibold text-depth">{report.headline}</p>
          <p className="font-mono text-xs text-depth/50">
            {new Date(reading.timestamp).toLocaleString(lang === "ar" ? "ar" : undefined, {
              dateStyle: "medium",
              timeStyle: "short",
            })}
          </p>
        </div>
      </div>

      <p className="mt-5 leading-relaxed text-depth/80">{report.overallSummary}</p>

      <h3 className="mb-3 mt-6 font-mono text-xs uppercase tracking-[0.16em] text-depth/50">
        {t("reports.biomarkers")}
      </h3>
      <div className="overflow-hidden rounded-xl border border-signal/15">
        <table className="w-full text-start text-sm">
          <thead className="bg-depth text-white">
            <tr>
              <th className="px-4 py-2.5 text-start font-semibold">{t("reports.biomarker")}</th>
              <th className="px-4 py-2.5 text-start font-semibold">{t("reports.value")}</th>
              <th className="px-4 py-2.5 text-start font-semibold">{t("dash.reference")}</th>
              <th className="px-4 py-2.5 text-start font-semibold">{t("reports.status")}</th>
            </tr>
          </thead>
          <tbody>
            {METRIC_KEYS.map((key, i) => {
              const m = reading.metrics[key];
              return (
                <tr key={key} className={i % 2 ? "bg-mist/60" : "bg-white"}>
                  <td className="px-4 py-2.5 font-medium">{t(`metric.${key}`)}</td>
                  <td className="px-4 py-2.5 font-mono tabular-nums" dir="ltr">
                    {formatValue(m.value, metricMeta[key].dp)}
                    {m.unit ? ` ${m.unit}` : ""}
                  </td>
                  <td className="px-4 py-2.5 font-mono text-depth/55" dir="ltr">
                    {m.range[0]}–{m.range[1]}
                  </td>
                  <td className="px-4 py-2.5 font-semibold" style={{ color: statusMeta[m.status].color }}>
                    {t(`status.${m.status}`)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <h3 className="mb-3 mt-6 font-mono text-xs uppercase tracking-[0.16em] text-depth/50">
        {t("reports.areaSummary")}
      </h3>
      <ul className="space-y-3">
        {report.areas?.map((a) => (
          <li key={a.id} className="rounded-xl border border-signal/15 bg-mist/40 p-3">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-depth">{t(`area.${a.id}`)}</span>
              <span className="text-xs font-semibold" style={{ color: statusMeta[a.status]?.color || "#241A44" }}>
                {t(`status.${a.status}`) || a.status}
              </span>
            </div>
            <p className="mt-1 text-sm leading-relaxed text-depth/70">{a.note}</p>
          </li>
        ))}
      </ul>

      {report.recommendation && (
        <p className="mt-5 rounded-xl bg-signal/8 p-4 text-sm leading-relaxed text-depth/80">
          {report.recommendation}
        </p>
      )}

      <p className="mt-6 border-t border-signal/15 pt-4 text-xs italic leading-relaxed text-depth/45">
        {report.disclaimer}
      </p>
    </div>
  );
}

export default function Reports() {
  const { t, lang } = useLang();
  const { reading, loading: readingLoading } = useLatestReading();
  const [report, setReport] = useState(null);
  // Multi-tenant (2026-08-19): a brand-new account can genuinely have zero
  // readings — this used to be impossible, so nothing here distinguished
  // "still fetching" from "loaded, and there's really nothing yet." Starts
  // false (not true) specifically so a no-reading account doesn't show the
  // "thinking" animation forever waiting on a report fetch that will never
  // even be attempted — see the effect below, gated on `reading`.
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const docRef = useRef(null);

  const loadReport = () => {
    if (!reading) return;
    setLoading(true);
    setError(false);
    getReport(lang)
      .then(setReport)
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadReport();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lang, reading]);

  const handleDownload = async () => {
    if (!docRef.current) return;
    setDownloading(true);
    setError(false);
    try {
      const stamp = new Date(reading.timestamp).toISOString().slice(0, 10);
      await generateReportPdf(docRef.current, `novera-screening-${lang}-${stamp}.pdf`);
      setDone(true);
      setTimeout(() => setDone(false), 4000);
    } catch (e) {
      console.error(e);
      setError(true);
    } finally {
      setDownloading(false);
    }
  };

  const isEmpty = !readingLoading && !loading && !reading;
  const busy = readingLoading || loading || !reading || !report;
  const disableActions = busy || isEmpty;

  return (
    <PageShell eyebrow={t("reports.eyebrow")} title={t("reports.title")} intro={t("reports.intro")}>
      <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr] lg:items-start">
        <div>
          {isEmpty ? (
            <div className="light-card flex flex-col items-center gap-4 px-6 py-16 text-center">
              <span className="flex h-14 w-14 items-center justify-center rounded-full bg-signal/10 text-signal">
                <Droplet size={26} strokeWidth={1.8} />
              </span>
              <div>
                <h2 className="font-display text-xl font-bold text-depth">{t("dash.emptyTitle")}</h2>
                <p className="mt-2 max-w-sm text-sm text-depth/60">{t("dash.emptyBody")}</p>
              </div>
            </div>
          ) : busy ? (
            <div className="light-card flex h-96 items-center justify-center">
              <AgentThinking />
            </div>
          ) : (
            <PrintableReport reading={reading} report={report} lang={lang} t={t} docRef={docRef} />
          )}
        </div>

        <div className="light-card p-6 lg:sticky lg:top-24">
          <div className="flex items-center justify-between">
            <h3 className="font-display text-lg font-semibold text-depth">{t("reports.download")}</h3>
            {report?.source && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-signal/10 px-2.5 py-1 font-mono text-[10px] uppercase tracking-wide text-signal">
                <Sparkles size={11} /> {report.source === "ai" ? t("reports.aiBadge") : t("reports.fallbackBadge")}
              </span>
            )}
          </div>

          <button type="button" onClick={handleDownload} disabled={disableActions || downloading} className="btn-primary mt-5 w-full disabled:opacity-60">
            {downloading ? <Loader2 size={18} className="animate-spin" /> : <Download size={18} />}
            {t("reports.download")}
          </button>
          <button type="button" onClick={loadReport} disabled={disableActions} className="btn-ghost mt-3 w-full !text-depth !border-depth/15 disabled:opacity-60">
            <RefreshCw size={16} /> {t("reports.regenerate")}
          </button>

          <div className="mt-4 min-h-[24px]" aria-live="polite">
            <AnimatePresence mode="wait">
              {done && (
                <motion.p key="ok" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="flex items-center justify-center gap-2 text-sm font-medium text-status-good">
                  <Check size={16} /> {t("reports.downloaded")}
                </motion.p>
              )}
              {error && (
                <motion.p key="err" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="flex items-center justify-center gap-2 text-sm font-medium text-status-attention">
                  <CircleAlert size={16} /> {t("common.retry")}
                </motion.p>
              )}
            </AnimatePresence>
          </div>

          {report?.source === "fallback" && (
            <p className="mt-2 text-xs italic text-depth/45">{t("aiOffline")}</p>
          )}
        </div>
      </div>
    </PageShell>
  );
}
