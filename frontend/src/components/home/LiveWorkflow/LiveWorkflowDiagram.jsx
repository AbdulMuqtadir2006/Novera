import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Check, AlertTriangle, Loader2 } from "lucide-react";
import { useLang } from "../../../i18n/LanguageContext";
import { usePrefersReducedMotion } from "../../../hooks/usePrefersReducedMotion";
import { useWorkflowSocket } from "../../../hooks/useWorkflowSocket";
import {
  CANVAS_W,
  CANVAS_H,
  WORKFLOW_NODES,
  NODE_BY_ID,
  WORKFLOW_EDGES,
  AGENT_SATELLITES,
  DEMO_SEQUENCE,
  ALL_NODE_IDS,
} from "../../../data/liveWorkflow";

const LIVE_WINDOW_MS = 90_000;
const DEMO_STEP_MS = 2800;
const EVENT_LOG_MAX = 5;

// Brand accents standing in for the reference screenshot's literal palette —
// same idle/running/passed/failed language PipelineVisualizer already uses
// elsewhere in this app, just applied to a bigger canvas. Amber (not red)
// for error, per design brief: a workflow hiccup isn't a health alert.
const STATUS_COLOR = {
  idle: "rgba(255,255,255,0.16)",
  active: "#28CFE0",
  success: "#3DDC97",
  error: "#F2A93E",
};

function idleStatusMap() {
  return Object.fromEntries(ALL_NODE_IDS.map((id) => [id, "idle"]));
}

function buildDemoStatus(stepIndex) {
  const status = idleStatusMap();
  for (let i = 0; i < stepIndex; i++) status[DEMO_SEQUENCE[i]] = "success";
  if (stepIndex >= 0 && stepIndex < DEMO_SEQUENCE.length) status[DEMO_SEQUENCE[stepIndex]] = "active";
  return status;
}

// A wire lights up as soon as its *source* finishes, even before the target
// has started — reads as "data already computed, now in transit" (matters
// most for the 3-way score fan-in, where two organs can finish while the
// third is still scoring). Once the target itself starts/finishes, the wire
// just mirrors the target's own state.
function edgeDisplayStatus(fromStatus, toStatus) {
  if (toStatus === "success" || toStatus === "error" || toStatus === "active") return toStatus;
  if (fromStatus === "success") return "active";
  return "idle";
}

function edgeAnchors(from, to) {
  const x1 = from.x + from.w / 2;
  const y1 = from.y;
  const x2 = to.x - to.w / 2;
  const y2 = to.y;
  const dx = Math.max(36, (x2 - x1) * 0.55);
  const d = `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
  return { d, x1, y1, x2, y2 };
}

function NodeIcon({ node, status, reducedMotion }) {
  const Icon = node.icon;
  const color = STATUS_COLOR[status];
  return (
    <span
      className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border"
      style={{
        borderColor: status === "idle" ? "rgba(255,255,255,0.12)" : color,
        backgroundColor: status === "idle" ? "rgba(255,255,255,0.03)" : `${color}1f`,
        boxShadow: status === "active" && !reducedMotion ? `0 0 16px -2px ${color}` : "none",
      }}
    >
      <Icon size={16} strokeWidth={1.9} style={{ color: status === "idle" ? "#6b7280" : color }} />
    </span>
  );
}

function StatusBadge({ status, reducedMotion }) {
  const color = STATUS_COLOR[status];
  if (status === "success") {
    return (
      <span
        className="flex h-4 w-4 items-center justify-center rounded-full"
        style={{ backgroundColor: color }}
      >
        <Check size={10} strokeWidth={3} className="text-ink" />
      </span>
    );
  }
  if (status === "active") {
    return <Loader2 size={14} className={reducedMotion ? "" : "animate-spin"} style={{ color }} />;
  }
  if (status === "error") {
    return <AlertTriangle size={13} style={{ color }} />;
  }
  return <span className="h-1.5 w-1.5 rounded-full bg-white/15" />;
}

// Guidance Agent is the actual decision-maker in the pipeline (the only node
// that chooses its own next step), so it gets a distinct "brain" treatment
// on top of the normal card chrome: a blurred radial aura that intensifies
// while active and settles once it decides, plus the same expanding-ring
// pulse AgentsSection/ComingSoon already use elsewhere for "this is alive."
function AgentCore({ status, color, reducedMotion }) {
  return (
    <>
      <span
        className={`pointer-events-none absolute -inset-4 rounded-[28px] blur-xl transition-opacity duration-500 ${
          status === "active" && !reducedMotion ? "animate-pulse" : ""
        }`}
        style={{
          background: `radial-gradient(circle, ${color}55 0%, transparent 72%)`,
          opacity: status === "idle" ? 0.12 : status === "success" ? 0.35 : 0.65,
        }}
        aria-hidden="true"
      />
      {status === "active" && !reducedMotion && (
        <span
          className="pointer-events-none absolute inset-0 animate-pulse-ring rounded-2xl border-2"
          style={{ borderColor: color }}
          aria-hidden="true"
        />
      )}
    </>
  );
}

function NodeCard({ node, status, big, reducedMotion, t }) {
  const color = STATUS_COLOR[status];
  const isAgent = node.id === "agent";

  // Tracks the *transition into* active so a node gets one punchier
  // "arrival" kick the moment it lights up, then settles into the regular
  // looping pulse — reads as a tool call actually landing, not just a
  // decorative loop that was always running.
  const prevStatusRef = useRef(status);
  const [justArrived, setJustArrived] = useState(false);
  useEffect(() => {
    const wasActive = prevStatusRef.current === "active";
    prevStatusRef.current = status;
    if (!wasActive && status === "active" && !reducedMotion) {
      setJustArrived(true);
      const timer = setTimeout(() => setJustArrived(false), 560);
      return () => clearTimeout(timer);
    }
    return undefined;
  }, [status, reducedMotion]);

  const animate = justArrived
    ? { scale: [1, 1.2, 0.96, 1.04, 1] }
    : status === "active" && !reducedMotion
      ? { scale: [1, 1.03, 1] }
      : { scale: 1 };
  const transition = justArrived
    ? { duration: 0.56, ease: "easeOut" }
    : status === "active" && !reducedMotion
      ? { duration: 1.1, repeat: Infinity, ease: "easeInOut" }
      : { duration: 0.3, ease: "easeOut" };

  return (
    <motion.div
      className="absolute flex items-center gap-2.5 rounded-2xl border bg-white/[0.03] px-3 backdrop-blur-sm"
      style={{
        left: node.x - node.w / 2,
        top: node.y - node.h / 2,
        width: node.w,
        height: node.h,
        borderColor: status === "idle" ? "rgba(255,255,255,0.10)" : `${color}66`,
        boxShadow: status === "idle" ? "none" : `0 0 24px -10px ${color}`,
      }}
      animate={animate}
      transition={transition}
      role="status"
      aria-label={`${t(node.labelKey)} — ${t(`liveWorkflow.state.${status}`)}`}
    >
      {isAgent && <AgentCore status={status} color={color} reducedMotion={reducedMotion} />}
      <NodeIcon node={node} status={status} reducedMotion={reducedMotion} />
      <span className="min-w-0 flex-1">
        <span
          className={`line-clamp-2 font-body text-[11.5px] font-semibold leading-[1.2] ${
            status === "idle" ? "text-slate-400" : "text-white"
          } ${big ? "sm:text-[13px]" : ""}`}
        >
          {t(node.labelKey)}
        </span>
      </span>
      <StatusBadge status={status} reducedMotion={reducedMotion} />
    </motion.div>
  );
}

function SatelliteChip({ sat, agent, t }) {
  const x = agent.x + sat.dx;
  const y = agent.y + sat.dy;
  const Icon = sat.icon;
  return (
    <div
      className="absolute flex w-[132px] -translate-x-1/2 flex-col items-center gap-1 rounded-xl border border-dashed border-iris/35 bg-white/[0.02] px-2.5 py-2 text-center"
      style={{ left: x, top: y }}
    >
      <Icon size={13} className="text-iris" strokeWidth={1.8} />
      <span className="font-mono text-[9px] uppercase tracking-wider text-slate-400">{t(sat.labelKey)}</span>
      <span className="text-[10px] leading-tight text-slate-500">{t(sat.detailKey)}</span>
    </div>
  );
}

// Active wires leave a short glowing "comet" trail instead of a bare dot —
// three copies of the same path animation, phase-offset via negative
// `begin`, shrinking in size/opacity from head to tail.
function Wire({ edge, status, reducedMotion }) {
  const from = NODE_BY_ID[edge.from];
  const to = NODE_BY_ID[edge.to];
  const { d } = edgeAnchors(from, to);
  const color = STATUS_COLOR[status];
  const pathId = `wire-${edge.id}`;
  const active = status === "active" && !reducedMotion;
  return (
    <g>
      <path d={d} fill="none" stroke="rgba(255,255,255,0.10)" strokeWidth={1.5} />
      {status !== "idle" && (
        <path id={pathId} d={d} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" opacity={0.85} />
      )}
      {active && (
        <>
          <circle r={6.5} fill={color} opacity={0.16} filter="url(#wireGlow)">
            <animateMotion dur="1.15s" begin="-0.18s" repeatCount="indefinite">
              <mpath xlinkHref={`#${pathId}`} />
            </animateMotion>
          </circle>
          <circle r={4.5} fill={color} opacity={0.4}>
            <animateMotion dur="1.15s" begin="-0.09s" repeatCount="indefinite">
              <mpath xlinkHref={`#${pathId}`} />
            </animateMotion>
          </circle>
          <circle r={3.5} fill={color}>
            <animateMotion dur="1.15s" repeatCount="indefinite">
              <mpath xlinkHref={`#${pathId}`} />
            </animateMotion>
          </circle>
        </>
      )}
    </g>
  );
}

function SatelliteWire({ sat, agent }) {
  const x1 = agent.x + sat.dx;
  const y1 = agent.y + agent.h / 2;
  const x2 = agent.x + sat.dx;
  const y2 = agent.y + sat.dy - 6;
  return (
    <path
      d={`M ${agent.x} ${y1} L ${x1} ${(y1 + y2) / 2} L ${x2} ${y2}`}
      fill="none"
      stroke="rgba(178,75,214,0.35)"
      strokeWidth={1.25}
      strokeDasharray="3 4"
    />
  );
}

function LiveIndicator({ isLive, t }) {
  return (
    <div className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.03] px-2.5 py-1">
      <span className="relative flex h-1.5 w-1.5">
        {isLive && (
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-status-good opacity-60" />
        )}
        <span
          className="relative inline-flex h-1.5 w-1.5 rounded-full"
          style={{ backgroundColor: isLive ? "#3DDC97" : "#6b7280" }}
        />
      </span>
      <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-400">
        {isLive ? t("liveWorkflow.status.live") : t("liveWorkflow.status.preview")}
      </span>
    </div>
  );
}

// Terminal/log-style strip replaying the real event labels as they stream
// in off the socket (highest-impact "the AI is visibly thinking" cue — real
// backend text reads as authentic in a way generic animation doesn't). Only
// ever shows genuine events: it goes quiet rather than fabricate activity
// when there's no live run to report on.
function EventTicker({ entries, isLive, reducedMotion, t }) {
  const hasEntries = isLive && entries.length > 0;
  return (
    <div
      className="relative overflow-hidden rounded-xl border border-white/10 bg-black/30 px-3 py-2"
      style={{ boxShadow: "inset 0 0 24px -8px rgba(40,207,224,0.25)" }}
      aria-hidden="true"
    >
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.05]"
        style={{
          backgroundImage:
            "repeating-linear-gradient(0deg, #fff 0px, #fff 1px, transparent 1px, transparent 3px)",
        }}
      />
      <p className="relative mb-1 font-mono text-[9px] uppercase tracking-[0.2em] text-slate-500">
        {t("liveWorkflow.ticker.label")}
      </p>
      {hasEntries ? (
        <ul className="relative flex flex-col gap-0.5">
          {entries.map((entry, i) => {
            const isLast = i === entries.length - 1;
            return (
              <motion.li
                key={entry.id}
                initial={reducedMotion ? false : { opacity: 0, x: -6 }}
                animate={{ opacity: isLast ? 1 : 0.3 + (i / entries.length) * 0.35, x: 0 }}
                transition={{ duration: 0.35, ease: "easeOut" }}
                className="truncate font-mono text-[10.5px] leading-snug text-signal/90"
              >
                <span className="text-slate-600">{">"}</span> {entry.label}
              </motion.li>
            );
          })}
        </ul>
      ) : (
        <p className="relative truncate font-mono text-[10.5px] leading-snug text-slate-500">
          <span className="text-slate-600">{">"}</span> {t("liveWorkflow.ticker.idle")}
        </p>
      )}
    </div>
  );
}

function WorkflowLive() {
  const { t } = useLang();
  const reducedMotion = usePrefersReducedMotion();
  const { connected, nodeStatus, currentLabel, lastEventAt } = useWorkflowSocket();

  const [isLive, setIsLive] = useState(false);
  useEffect(() => {
    if (!connected || !lastEventAt) {
      setIsLive(false);
      return undefined;
    }
    const remaining = LIVE_WINDOW_MS - (Date.now() - lastEventAt);
    if (remaining <= 0) {
      setIsLive(false);
      return undefined;
    }
    setIsLive(true);
    const timer = setTimeout(() => setIsLive(false), remaining);
    return () => clearTimeout(timer);
  }, [connected, lastEventAt]);

  const [demoStep, setDemoStep] = useState(0);
  useEffect(() => {
    if (isLive) return undefined;
    const interval = setInterval(() => {
      setDemoStep((s) => (s + 1) % (DEMO_SEQUENCE.length + 2));
    }, DEMO_STEP_MS);
    return () => clearInterval(interval);
  }, [isLive]);

  const demoStatus = useMemo(() => buildDemoStatus(demoStep), [demoStep]);
  const status = isLive ? nodeStatus : demoStatus;

  // Rolling local history of real event labels for the ticker — the hook
  // only exposes the single latest label, so we accumulate our own capped
  // window here, keyed off `lastEventAt` so we never double-log a render
  // that didn't actually carry a new event. Cleared whenever we drop out of
  // "live" so a stale run's chatter never lingers into preview mode.
  const [eventLog, setEventLog] = useState([]);
  const lastLoggedAtRef = useRef(null);
  useEffect(() => {
    if (!isLive) {
      lastLoggedAtRef.current = null;
      setEventLog([]);
      return;
    }
    if (!currentLabel || !lastEventAt || lastEventAt === lastLoggedAtRef.current) return;
    lastLoggedAtRef.current = lastEventAt;
    setEventLog((prev) => [...prev, { id: `${lastEventAt}`, label: currentLabel }].slice(-EVENT_LOG_MAX));
  }, [isLive, currentLabel, lastEventAt]);

  const agentNode = NODE_BY_ID.agent;
  const caption = isLive
    ? currentLabel
    : t(`liveWorkflow.node.${keyOf(DEMO_SEQUENCE[Math.min(demoStep, DEMO_SEQUENCE.length - 1)])}`);

  // Scale-to-fit: measure the real available width and shrink the fixed
  // CANVAS_W x CANVAS_H canvas with a CSS transform so it always fits
  // without ever needing horizontal scroll — recomputed on resize via
  // ResizeObserver, capped at 1 so it never scales up past its natural size.
  const measureRef = useRef(null);
  const [scale, setScale] = useState(1);
  useLayoutEffect(() => {
    const el = measureRef.current;
    if (!el) return undefined;

    const measure = () => {
      const width = el.clientWidth;
      if (width > 0) setScale(Math.min(1, width / CANVAS_W));
    };
    measure();

    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", measure);
      return () => window.removeEventListener("resize", measure);
    }
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div className="flex w-full flex-col pb-4">
      <div className="flex items-center justify-between px-4 pt-3 sm:px-5">
        <LiveIndicator isLive={isLive} t={t} />
        <p className="truncate pl-3 text-right font-mono text-[10px] text-slate-500 sm:text-[11px]">{caption}</p>
      </div>

      <div className="px-4 pt-2.5 sm:px-5">
        <EventTicker entries={eventLog} isLive={isLive} reducedMotion={reducedMotion} t={t} />
      </div>

      <div className="overflow-hidden px-2 pt-3 sm:px-4">
        <div ref={measureRef} className="w-full">
          <div className="relative mx-auto" style={{ width: CANVAS_W * scale, height: CANVAS_H * scale }}>
            <div
              className="absolute left-0 top-0 origin-top-left"
              style={{ width: CANVAS_W, height: CANVAS_H, transform: `scale(${scale})` }}
            >
              {/* Ambient atmosphere — the canvas stays faintly alive even
                  between discrete events, not just static except mid-transition. */}
              <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
                {!reducedMotion && (
                  <>
                    <span className="absolute -left-10 top-6 h-56 w-56 animate-drift-a rounded-full bg-signal/[0.05] blur-[80px]" />
                    <span className="absolute -right-10 bottom-0 h-64 w-64 animate-drift-b rounded-full bg-vital/[0.05] blur-[90px]" />
                  </>
                )}
              </div>

              <svg
                width={CANVAS_W}
                height={CANVAS_H}
                viewBox={`0 0 ${CANVAS_W} ${CANVAS_H}`}
                className="absolute inset-0"
                aria-hidden="true"
              >
                <defs>
                  <filter id="wireGlow" x="-200%" y="-200%" width="500%" height="500%">
                    <feGaussianBlur stdDeviation="2.4" />
                  </filter>
                </defs>
                {AGENT_SATELLITES.map((sat) => (
                  <SatelliteWire key={sat.id} sat={sat} agent={agentNode} />
                ))}
                {WORKFLOW_EDGES.map((edge) => (
                  <Wire
                    key={edge.id}
                    edge={edge}
                    status={edgeDisplayStatus(status[edge.from] ?? "idle", status[edge.to] ?? "idle")}
                    reducedMotion={reducedMotion}
                  />
                ))}
              </svg>

              {WORKFLOW_NODES.map((node) => (
                <NodeCard
                  key={node.id}
                  node={node}
                  status={status[node.id] ?? "idle"}
                  big={node.id === "agent"}
                  reducedMotion={reducedMotion}
                  t={t}
                />
              ))}

              {AGENT_SATELLITES.map((sat) => (
                <SatelliteChip key={sat.id} sat={sat} agent={agentNode} t={t} />
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function keyOf(nodeId) {
  return nodeId
    .split("_")
    .map((part, i) => (i === 0 ? part : part[0].toUpperCase() + part.slice(1)))
    .join("");
}

// Lazy-mounts the live/animated canvas only once the section is actually
// visible (same discipline as AgentFlow3D — no reason to open a WebSocket
// or run rAF-driven pulses for a visitor who never scrolls this far).
const IO_OPTIONS = { rootMargin: "200px 0px", threshold: 0.01 };

export function LiveWorkflowDiagram() {
  const containerRef = useRef(null);
  const [hasLoaded, setHasLoaded] = useState(false);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof IntersectionObserver === "undefined") {
      setHasLoaded(true);
      return undefined;
    }
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setHasLoaded(true);
        observer.disconnect();
      }
    }, IO_OPTIONS);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={containerRef} className="w-full">
      {hasLoaded ? (
        <WorkflowLive />
      ) : (
        <div className="h-[320px] w-full sm:h-[420px]" aria-hidden="true" />
      )}
    </div>
  );
}
