import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  MessageCircle, Send, Loader2, MapPin, Phone, CalendarCheck, Brain, Sparkles, ExternalLink,
} from "lucide-react";
import { PageShell } from "../components/layout/PageShell";
import {
  sendAppointmentOffer, replyAppointment, getBookings, getClinic, predictOrgan,
} from "../lib/api";
import { useLang } from "../i18n/LanguageContext";
import { useAuth } from "../auth/AuthContext";

const ORGAN_COLORS = { KIDNEY: "#28CFE0", STOMACH: "#F2A93E", ORAL: "#3DDC97" };

function OrganAnalysis({ t }) {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const run = async () => {
    setLoading(true);
    try {
      setResult(await predictOrgan());
    } catch {
      setResult({ error: true });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="light-card p-6">
      <h3 className="flex items-center gap-2 font-display text-lg font-semibold text-depth">
        <Brain size={18} className="text-signal" /> {t("appt.organTitle")}
      </h3>
      <p className="mt-1 text-sm text-depth/60">{t("appt.organHint")}</p>
      <button type="button" onClick={run} disabled={loading} className="btn-primary mt-4 disabled:opacity-60">
        {loading ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
        {loading ? t("appt.analysing") : t("appt.runAnalysis")}
      </button>

      {result && !result.error && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mt-5">
          <div className="flex items-baseline justify-between">
            <span className="font-mono text-[11px] uppercase tracking-wide text-depth/45">{t("appt.predicted")}</span>
            <span className="font-mono text-xs text-depth/50">
              {Math.round((result.confidence || 0) * 100)}% {t("appt.confidence")}
            </span>
          </div>
          <p className="mt-1 font-display text-2xl font-bold" style={{ color: ORGAN_COLORS[result.prediction] || "#241A44" }}>
            {result.prediction}
          </p>
          <p className="mt-2 text-sm leading-relaxed text-depth/70">{result.reason}</p>
          <div className="mt-4 space-y-2">
            {(result.specialist_results || []).map((s) => (
              <div key={s.organ}>
                <div className="flex justify-between text-xs text-depth/60">
                  <span>{s.organ}</span>
                  <span className="font-mono">{s.combined_score}</span>
                </div>
                <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-depth/10">
                  <div className="h-full rounded-full" style={{ width: `${Math.round(s.combined_score * 100)}%`, backgroundColor: ORGAN_COLORS[s.organ] || "#28CFE0" }} />
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      )}
    </div>
  );
}

export default function Appointments() {
  const { t, lang } = useLang();
  const { user } = useAuth();
  const [offer, setOffer] = useState(null);
  const [offering, setOffering] = useState(false);
  const [input, setInput] = useState("");
  const [thread, setThread] = useState([]);
  const [sending, setSending] = useState(false);
  const [bookings, setBookings] = useState([]);
  const [clinic, setClinic] = useState(null);

  const loadBookings = () => getBookings().then((b) => setBookings(Array.isArray(b) ? b : b.bookings || [])).catch(() => {});

  useEffect(() => {
    loadBookings();
    getClinic().then(setClinic).catch(() => {});
  }, []);

  const doOffer = async () => {
    setOffering(true);
    try {
      const r = await sendAppointmentOffer({ simulate: true });
      setOffer(r);
      setThread((tr) => [...tr, { role: "assistant", content: r.message }]);
    } finally {
      setOffering(false);
    }
  };

  const doReply = async (e) => {
    e.preventDefault();
    const msg = input.trim();
    if (!msg || sending) return;
    setInput("");
    setThread((tr) => [...tr, { role: "user", content: msg }]);
    setSending(true);
    try {
      const r = await replyAppointment(msg, lang);
      setThread((tr) => [...tr, { role: "assistant", content: r.reply }]);
      if (r.booking) loadBookings();
    } finally {
      setSending(false);
    }
  };

  return (
    <PageShell eyebrow={t("appt.eyebrow")} title={t("appt.title")} intro={t("appt.intro")}>
      <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr] lg:items-start">
        {/* WhatsApp flow */}
        <div className="space-y-6">
          <div className="light-card p-6">
            <h3 className="flex items-center gap-2 font-display text-lg font-semibold text-depth">
              <MessageCircle size={18} className="text-signal" /> {t("appt.offerTitle")}
            </h3>
            <p className="mt-1 text-sm text-depth/60">{t("appt.offerHint")}</p>
            {user?.phone && (
              <p className="mt-2 font-mono text-xs text-depth/50">
                {t("appt.sendingTo")}: <span className="text-depth/80">{user.phone}</span>
              </p>
            )}
            <button type="button" onClick={doOffer} disabled={offering} className="btn-primary mt-4 disabled:opacity-60">
              {offering ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
              {offering ? t("appt.sending") : t("appt.sendOffer")}
            </button>
            {offer && (
              <div className="mt-4 rounded-2xl border border-signal/15 bg-mist/50 p-4">
                <p className="mb-2 font-mono text-[11px] uppercase tracking-wide text-depth/45">{t("appt.simNote")}</p>
                <p className="whitespace-pre-line text-sm text-depth/80">{offer.message}</p>
              </div>
            )}
          </div>

          <div className="light-card flex flex-col p-6">
            <h3 className="flex items-center gap-2 font-display text-lg font-semibold text-depth">
              <MessageCircle size={18} className="text-signal" /> {t("appt.replyTitle")}
            </h3>
            <p className="mt-1 text-sm text-depth/60">{t("appt.replyHint")}</p>

            <div className="mt-4 flex max-h-80 min-h-[6rem] flex-col gap-3 overflow-y-auto pe-1">
              <AnimatePresence initial={false}>
                {thread.map((m, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    className={`max-w-[88%] whitespace-pre-line rounded-2xl px-3.5 py-2 text-sm leading-relaxed ${
                      m.role === "user" ? "self-end bg-depth text-white" : "self-start bg-signal/10 text-depth"
                    }`}
                  >
                    {m.content}
                  </motion.div>
                ))}
              </AnimatePresence>
              {sending && (
                <div className="self-start rounded-2xl bg-signal/10 px-3.5 py-2 text-sm text-depth/60">
                  <Loader2 size={14} className="inline animate-spin" /> {t("appt.thinking")}
                </div>
              )}
            </div>

            <form onSubmit={doReply} className="mt-4 flex gap-2">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={t("appt.replyPlaceholder")}
                className="min-w-0 flex-1 rounded-full border border-depth/15 bg-paper px-4 py-2.5 text-sm text-depth outline-none transition focus:border-signal"
              />
              <button type="submit" disabled={sending || !input.trim()} className="btn-primary shrink-0 !px-4 disabled:opacity-50" aria-label={t("appt.send")}>
                <Send size={18} />
              </button>
            </form>
          </div>
        </div>

        {/* Side: analysis + clinic + bookings */}
        <div className="space-y-6">
          <OrganAnalysis t={t} />

          {clinic && (
            <div className="light-card p-6">
              <h3 className="font-display text-lg font-semibold text-depth">{t("appt.clinicTitle")}</h3>
              <p className="mt-2 font-semibold text-depth">{clinic.name} — {clinic.branch}</p>
              <p className="mt-1 flex items-start gap-2 text-sm text-depth/70"><MapPin size={15} className="mt-0.5 shrink-0 text-signal" />{clinic.address}</p>
              <p className="mt-1 flex items-center gap-2 text-sm text-depth/70"><Phone size={15} className="text-signal" />{clinic.phone}</p>
              <a href={clinic.maps_url} target="_blank" rel="noopener noreferrer" className="mt-3 inline-flex items-center gap-1.5 text-sm font-medium text-signal hover:underline">
                <ExternalLink size={14} /> {t("appt.openMaps")}
              </a>
            </div>
          )}

          <div className="light-card p-6">
            <h3 className="flex items-center gap-2 font-display text-lg font-semibold text-depth">
              <CalendarCheck size={18} className="text-signal" /> {t("appt.bookingsTitle")}
            </h3>
            {bookings.length === 0 ? (
              <p className="mt-3 text-sm text-depth/45">{t("appt.noBookings")}</p>
            ) : (
              <ul className="mt-3 space-y-2">
                {[...bookings].reverse().map((b, i) => (
                  <li key={i} className="rounded-xl border border-signal/15 bg-paper px-3.5 py-2.5">
                    <p className="text-sm font-semibold text-depth">{b.when_human}</p>
                    <p className="text-xs text-depth/55">{b.clinic} — {b.branch}</p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </PageShell>
  );
}
