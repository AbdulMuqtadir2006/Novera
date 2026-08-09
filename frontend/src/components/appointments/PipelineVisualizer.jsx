import { motion } from "framer-motion";
import { Check, X, Loader2 } from "lucide-react";
import { useLang } from "../../i18n/LanguageContext";

const SCORE_ORGANS = ["score:KIDNEY", "score:STOMACH", "score:ORAL"];

// status.good / status.watch(unused here) / status.attention — same tokens
// StatusBadge already uses, so passed/failed reads consistently with the
// rest of the app (Dashboard's StatusBadge, ScreeningGauge, etc).
const STATUS_COLOR = {
  idle: "#241A44",
  running: "#28CFE0",
  passed: "#3DDC97",
  failed: "#FF5D5D",
};

function NodeDot({ label, state }) {
  const color = STATUS_COLOR[state] ?? STATUS_COLOR.idle;
  const dim = state === "idle";
  return (
    <div className="flex flex-col items-center gap-1.5">
      <motion.div
        className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-full border-2"
        style={{
          borderColor: dim ? "rgba(36,26,68,0.15)" : color,
          backgroundColor: dim ? "transparent" : `${color}1f`,
        }}
        animate={state === "running" ? { scale: [1, 1.12, 1] } : { scale: 1 }}
        transition={
          state === "running"
            ? { duration: 1, repeat: Infinity, ease: "easeInOut" }
            : { duration: 0.3, ease: "easeOut" }
        }
      >
        {state === "passed" && <Check size={16} style={{ color }} strokeWidth={3} />}
        {state === "failed" && <X size={16} style={{ color }} strokeWidth={3} />}
        {state === "running" && <Loader2 size={14} className="animate-spin" style={{ color }} />}
        {dim && <span className="h-1.5 w-1.5 rounded-full bg-depth/20" />}
      </motion.div>
      <span className={`text-center text-[11px] font-medium leading-tight ${dim ? "text-depth/40" : "text-depth/80"}`}>
        {label}
      </span>
    </div>
  );
}

function Connector({ active, failed }) {
  const color = failed ? STATUS_COLOR.failed : STATUS_COLOR.running;
  return (
    <div className="relative mx-1 h-0.5 min-w-[18px] flex-1 self-center overflow-hidden rounded-full bg-depth/10">
      <motion.div
        className="absolute inset-y-0 left-0 rounded-full"
        style={{ backgroundColor: color }}
        initial={false}
        animate={{ width: active ? "100%" : "0%" }}
        transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
      />
    </div>
  );
}

// Real hierarchy, not a flat pipe: Validate -> a grouped parallel Score step
// (Kidney/Stomach/Oral, the three sub-agents that actually run under it) ->
// Decide -> Persist. Node/connector state comes straight from real backend
// SSE events (see lib/api.js streamPredictOrgan) — idle/running/passed/failed
// — never a timer. A failed step (validation error or the OpenRouter call
// failing) turns visibly red and halts the chain rather than continuing.
export function PipelineVisualizer({ steps }) {
  const { t } = useLang();
  const s = (id) => steps[id] || "idle";

  const scoreStarted = SCORE_ORGANS.some((id) => s(id) !== "idle");
  const scoreFailed = SCORE_ORGANS.some((id) => s(id) === "failed");
  const scoreDone = SCORE_ORGANS.every((id) => s(id) === "passed");
  const scoreGroupState = scoreFailed ? "failed" : scoreDone ? "passed" : scoreStarted ? "running" : "idle";

  return (
    <div className="rounded-2xl border border-signal/15 bg-mist/50 p-4 sm:p-5">
      {/* Six nodes + connectors don't fit a phone width — scroll the diagram
          in its own track rather than let the page's blanket overflow-x:
          hidden silently clip nodes off the right edge. */}
      <div className="overflow-x-auto pb-1">
        <div className="flex w-max min-w-full items-start">
        <NodeDot label={t("appt.stepValidate")} state={s("validate")} />
        <Connector active={s("validate") !== "idle"} failed={s("validate") === "failed"} />

        <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-signal/25 px-2.5 py-2 sm:px-3">
          <span className="font-mono text-[9px] uppercase tracking-wider text-depth/40">
            {t("appt.stepScoreGroup")}
          </span>
          <div className="flex gap-3 sm:gap-4">
            <NodeDot label={t("appt.stepKidney")} state={s("score:KIDNEY")} />
            <NodeDot label={t("appt.stepStomach")} state={s("score:STOMACH")} />
            <NodeDot label={t("appt.stepOral")} state={s("score:ORAL")} />
          </div>
        </div>

        <Connector active={scoreGroupState !== "idle"} failed={scoreGroupState === "failed"} />
        <NodeDot label={t("appt.stepDecide")} state={s("decide")} />
          <Connector active={s("decide") === "passed" || s("persist") !== "idle"} failed={s("decide") === "failed"} />
          <NodeDot label={t("appt.stepPersist")} state={s("persist")} />
        </div>
      </div>
    </div>
  );
}
