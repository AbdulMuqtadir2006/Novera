import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, Send, Loader2, RefreshCw, Stethoscope, UtensilsCrossed } from "lucide-react";
import { PageShell } from "../components/layout/PageShell";
import { getSelfCare, getChat, sendChat } from "../lib/api";
import { healthAreaById } from "../data/healthAreas";
import { statusMeta } from "../lib/format";
import { useLang } from "../i18n/LanguageContext";
import { MealTimeline } from "../components/selfcare/MealTimeline";

const MEALS = ["breakfast", "lunch", "dinner", "snacks", "hydration"];

function DietPlan({ plan, t }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {MEALS.map((meal) => (
        <div key={meal} className="rounded-2xl border border-signal/15 bg-paper p-4">
          <p className="font-mono text-[11px] uppercase tracking-wide text-signal">{t(`selfcare.${meal}`)}</p>
          <p className="mt-1.5 text-sm leading-relaxed text-depth/80">{plan?.[meal]}</p>
        </div>
      ))}
    </div>
  );
}

function Coach({ lang, t, onContextChange }) {
  const [messages, setMessages] = useState([]);
  const [context, setContext] = useState({ diagnosis: "", medications: "", notes: "" });
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    getChat()
      .then((r) => {
        setMessages(r.messages || []);
        setContext(r.context || {});
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  const send = async (e) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: text }]);
    setSending(true);
    try {
      const r = await sendChat(text, lang);
      setMessages((m) => [...m, { role: "assistant", content: r.reply }]);
      setContext(r.context || context);
      if (r.contextChanged) onContextChange?.();
    } catch {
      setMessages((m) => [...m, { role: "assistant", content: t("common.retry") }]);
    } finally {
      setSending(false);
    }
  };

  const hasContext = context.diagnosis || context.medications || context.notes;

  return (
    <div className="light-card flex flex-col p-6">
      <h3 className="flex items-center gap-2 font-display text-lg font-semibold text-depth">
        <Stethoscope size={18} className="text-signal" /> {t("selfcare.coach")}
      </h3>
      <p className="mt-1 text-sm text-depth/60">{t("selfcare.coachHint")}</p>

      <div ref={scrollRef} className="mt-4 flex max-h-72 min-h-[8rem] flex-col gap-3 overflow-y-auto pe-1">
        <AnimatePresence initial={false}>
          {messages.map((m, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className={`max-w-[85%] rounded-2xl px-3.5 py-2 text-sm leading-relaxed ${
                m.role === "user"
                  ? "self-end bg-depth text-white"
                  : "self-start bg-signal/10 text-depth"
              }`}
            >
              {m.content}
            </motion.div>
          ))}
        </AnimatePresence>
        {sending && (
          <div className="self-start rounded-2xl bg-signal/10 px-3.5 py-2 text-sm text-depth/60">
            <Loader2 size={14} className="inline animate-spin" /> {t("selfcare.thinking")}
          </div>
        )}
      </div>

      <form onSubmit={send} className="mt-4 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={t("selfcare.inputPlaceholder")}
          className="min-w-0 flex-1 rounded-full border border-depth/15 bg-paper px-4 py-2.5 text-sm text-depth outline-none transition focus:border-signal"
        />
        <button type="submit" disabled={sending || !input.trim()} className="btn-primary shrink-0 !px-4 disabled:opacity-50" aria-label={t("selfcare.send")}>
          <Send size={18} />
        </button>
      </form>

      <div className="mt-5 border-t border-signal/10 pt-4">
        <p className="font-mono text-[11px] uppercase tracking-wide text-depth/45">{t("selfcare.contextTitle")}</p>
        {hasContext ? (
          <dl className="mt-2 space-y-1.5 text-sm">
            {context.diagnosis && (
              <div><dt className="inline font-semibold text-depth">{t("selfcare.diagnosis")}: </dt><dd className="inline text-depth/70">{context.diagnosis}</dd></div>
            )}
            {context.medications && (
              <div><dt className="inline font-semibold text-depth">{t("selfcare.medications")}: </dt><dd className="inline text-depth/70">{context.medications}</dd></div>
            )}
            {context.notes && (
              <div><dt className="inline font-semibold text-depth">{t("selfcare.notes")}: </dt><dd className="inline text-depth/70">{context.notes}</dd></div>
            )}
          </dl>
        ) : (
          <p className="mt-2 text-sm text-depth/45">{t("selfcare.noContext")}</p>
        )}
      </div>
    </div>
  );
}

export default function SelfCare() {
  const { t, lang } = useLang();
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadPlan = () => {
    setLoading(true);
    getSelfCare(lang)
      .then(setPlan)
      .catch(() => setPlan(null))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadPlan();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lang]);

  return (
    <PageShell eyebrow={t("selfcare.eyebrow")} title={t("selfcare.title")} intro={t("selfcare.intro")}>
      <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr] lg:items-start">
        {/* Plan column */}
        <div className="space-y-6">
          {loading || !plan ? (
            <div className="light-card flex h-72 items-center justify-center">
              <p className="flex items-center gap-2 text-depth/60">
                <Loader2 size={18} className="animate-spin" /> {t("selfcare.generating")}
              </p>
            </div>
          ) : (
            <>
              <motion.div
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                className="relative overflow-hidden rounded-3xl bg-depth p-7 text-white"
              >
                <div className="pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full bg-signal/20 blur-3xl" aria-hidden="true" />
                <p className="relative flex items-center gap-2 font-mono text-xs uppercase tracking-[0.2em] text-signal">
                  <Sparkles size={14} /> {t("selfcare.todaysFocus")}
                </p>
                <h2 className="relative mt-4 font-display text-2xl font-bold sm:text-3xl">{plan.focusTitle}</h2>
                <p className="relative mt-3 max-w-2xl leading-relaxed text-slate-300">{plan.focusBody}</p>
              </motion.div>

              <MealTimeline plan={plan} t={t} lang={lang} />

              <div>
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="flex items-center gap-2 font-display text-lg font-bold text-depth">
                    <UtensilsCrossed size={18} className="text-signal" /> {t("selfcare.dietPlan")}
                  </h3>
                  <div className="flex items-center gap-3">
                    {plan.source && (
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-signal/10 px-2.5 py-1 font-mono text-[10px] uppercase tracking-wide text-signal">
                        <Sparkles size={11} /> {plan.source === "ai" ? t("reports.aiBadge") : t("reports.fallbackBadge")}
                      </span>
                    )}
                    <button type="button" onClick={loadPlan} className="inline-flex items-center gap-1.5 text-sm font-medium text-depth/60 transition hover:text-depth">
                      <RefreshCw size={14} /> {t("selfcare.regenerate")}
                    </button>
                  </div>
                </div>
                <DietPlan plan={plan.dietPlan} t={t} />
              </div>

              <div>
                <h3 className="mb-3 font-display text-lg font-bold text-depth">{t("selfcare.areaTips")}</h3>
                <div className="grid gap-3 sm:grid-cols-2">
                  {plan.areaTips?.map((a) => {
                    const Icon = healthAreaById[a.id]?.icon;
                    const color = statusMeta[a.status]?.color || "#241A44";
                    return (
                      <div key={a.id} className="light-card p-4">
                        <div className="flex items-center gap-2.5">
                          {Icon && (
                            <span className="flex h-9 w-9 items-center justify-center rounded-lg" style={{ backgroundColor: `${color}1a`, color }}>
                              <Icon size={18} strokeWidth={1.75} />
                            </span>
                          )}
                          <span className="font-semibold text-depth">{t(`area.${a.id}`)}</span>
                        </div>
                        <p className="mt-2 text-sm leading-relaxed text-depth/70">{a.tip}</p>
                      </div>
                    );
                  })}
                </div>
              </div>

              <p className="text-xs italic text-depth/45">{t("selfcare.disclaimer")}</p>
            </>
          )}
        </div>

        {/* Coach column */}
        <div className="lg:sticky lg:top-24">
          <Coach lang={lang} t={t} onContextChange={loadPlan} />
        </div>
      </div>
    </PageShell>
  );
}
