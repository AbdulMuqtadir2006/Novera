import { useEffect, useState } from "react";
import { Play, Pause, RotateCcw, Volume2, TriangleAlert, Sparkles } from "lucide-react";
import { PageShell } from "../components/layout/PageShell";
import { VoiceOrb } from "../components/voice/VoiceOrb";
import { AgentThinking } from "../components/ui/AgentThinking";
import { useSpeech } from "../hooks/useSpeech";
import { getVoiceScript } from "../lib/api";
import { useLang } from "../i18n/LanguageContext";

export default function Voice() {
  const { t, lang } = useLang();
  const [script, setScript] = useState("");
  const [source, setSource] = useState(null);
  const [loading, setLoading] = useState(true);

  const {
    supported,
    speaking,
    paused,
    charIndex,
    boundaryPulse,
    hasVoiceForLang,
    failed,
    play,
    pause,
    resume,
    stop,
  } = useSpeech(script, lang);

  // (Re)generate the script whenever the language changes.
  useEffect(() => {
    let alive = true;
    setLoading(true);
    stop();
    getVoiceScript(lang)
      .then((r) => {
        if (!alive) return;
        setScript(r.script || "");
        setSource(r.source);
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lang]);

  const active = speaking && !paused;
  const spoken = script.slice(0, charIndex);
  const rest = script.slice(charIndex);

  return (
    <PageShell eyebrow={t("voice.eyebrow")} title={t("voice.title")} intro={t("voice.intro")}>
      <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr] lg:items-start">
        <div className="light-card flex flex-col items-center gap-8 p-8">
          <VoiceOrb active={active} pulseKey={boundaryPulse} />

          {loading ? (
            <AgentThinking />
          ) : supported ? (
            <div className="flex flex-wrap items-center justify-center gap-3">
              {!speaking && (
                <button type="button" onClick={play} className="btn-primary" disabled={!script}>
                  <Play size={18} /> {t("voice.play")}
                </button>
              )}
              {speaking && !paused && (
                <button type="button" onClick={pause} className="inline-flex items-center gap-2 rounded-full border border-depth/15 bg-paper px-6 py-3 font-semibold text-depth transition hover:border-signal/50">
                  <Pause size={18} /> {t("voice.pause")}
                </button>
              )}
              {speaking && paused && (
                <button type="button" onClick={resume} className="btn-primary">
                  <Play size={18} /> {t("voice.resume")}
                </button>
              )}
              <button
                type="button"
                onClick={play}
                aria-label={t("voice.replay")}
                className="inline-flex h-12 w-12 items-center justify-center rounded-full border border-depth/15 bg-paper text-depth transition hover:border-signal/50"
                disabled={!script}
              >
                <RotateCcw size={18} />
              </button>
            </div>
          ) : (
            <p className="flex items-center gap-2 text-sm text-status-watch">
              <TriangleAlert size={16} /> {t("voice.unsupported")}
            </p>
          )}

          <p className="flex items-center gap-2 font-mono text-xs uppercase tracking-[0.16em] text-depth/45">
            <Volume2 size={14} />
            {active ? t("voice.speaking") : paused ? t("voice.paused") : t("voice.idle")}
          </p>
          {failed && (
            <p className="flex items-center gap-1.5 text-center text-xs font-medium text-status-attention">
              <TriangleAlert size={13} /> {t("voice.playbackFailed")}
            </p>
          )}
          {supported && lang === "ar" && !hasVoiceForLang && !failed && (
            <p className="text-center text-xs text-status-watch">{t("voice.noArabicVoice")}</p>
          )}
        </div>

        <div className="light-card p-6 sm:p-8">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-mono text-xs uppercase tracking-[0.16em] text-depth/50">{t("voice.transcript")}</h2>
            {source && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-signal/10 px-2.5 py-1 font-mono text-[10px] uppercase tracking-wide text-signal">
                <Sparkles size={11} /> {source === "ai" ? t("reports.aiBadge") : t("reports.fallbackBadge")}
              </span>
            )}
          </div>
          {loading ? (
            <div className="space-y-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="h-4 animate-pulse rounded bg-depth/10" style={{ width: `${90 - i * 12}%` }} />
              ))}
            </div>
          ) : (
            <p className="text-lg leading-relaxed text-depth/40">
              <span className="text-depth">{spoken}</span>
              <span>{rest}</span>
            </p>
          )}
          {source === "fallback" && !loading && (
            <p className="mt-6 border-t border-signal/10 pt-4 text-xs italic text-depth/45">{t("aiOffline")}</p>
          )}
        </div>
      </div>
    </PageShell>
  );
}
