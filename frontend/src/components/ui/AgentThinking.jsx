import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Radar, GitCompareArrows, MessageSquareText, Compass } from "lucide-react";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";
import { useLang } from "../../i18n/LanguageContext";

const EASE = [0.16, 1, 0.3, 1];
const STAGE_MS = 3600;

const STAGES = [
  { id: "capture", icon: Radar },
  { id: "analysis", icon: GitCompareArrows },
  { id: "insight", icon: MessageSquareText },
  { id: "guidance", icon: Compass },
];

/**
 * Long-wait indicator for AI-backed calls (voice script, self-care plan,
 * report — can take up to ~60s on a cold OpenRouter response before the
 * backend's own timeout falls back to a deterministic answer). A bare
 * spinner reads as broken past a few seconds; this narrates the same
 * four-agent pipeline shown on the homepage so the wait reinforces the
 * product story instead of just stalling. Purely time-paced, not a claim
 * of real backend progress — the last stage holds and pulses instead of
 * resetting, since we don't know exactly when the response will land.
 */
export function AgentThinking({ className = "" }) {
  const { t } = useLang();
  const reduced = usePrefersReducedMotion();
  const [stage, setStage] = useState(0);
  const onLastStage = stage === STAGES.length - 1;

  useEffect(() => {
    if (onLastStage) return;
    const id = setTimeout(() => setStage((s) => s + 1), STAGE_MS);
    return () => clearTimeout(id);
  }, [stage, onLastStage]);

  const current = STAGES[stage];
  const Icon = current.icon;

  return (
    <div className={`flex flex-col items-center gap-5 ${className}`}>
      <div className="flex items-center gap-2">
        {STAGES.map((s, i) => (
          <span key={s.id} className="relative h-1.5 w-8 overflow-hidden rounded-full bg-depth/10">
            <motion.span
              className="absolute inset-y-0 left-0 rounded-full bg-signal"
              initial={false}
              animate={
                i < stage
                  ? { width: "100%" }
                  : i > stage
                  ? { width: "0%" }
                  : onLastStage && !reduced
                  ? { width: ["45%", "88%", "60%", "88%"] }
                  : { width: "100%" }
              }
              transition={
                i === stage && onLastStage && !reduced
                  ? { duration: 2.4, repeat: Infinity, ease: "easeInOut" }
                  : { duration: 0.5, ease: EASE }
              }
            />
          </span>
        ))}
      </div>

      <AnimatePresence mode="wait">
        <motion.div
          key={current.id}
          initial={reduced ? false : { opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={reduced ? {} : { opacity: 0, y: -6 }}
          transition={{ duration: 0.35, ease: EASE }}
          className="flex items-center gap-2.5"
        >
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-signal/12 text-signal">
            <Icon size={14} />
          </span>
          <span className="text-sm text-depth/70">{t(`thinking.${current.id}`)}…</span>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
