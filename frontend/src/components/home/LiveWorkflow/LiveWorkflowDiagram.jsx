import { useEffect, useMemo, useRef, useState } from "react";
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

function NodeCard({ node, status, big, reducedMotion, t }) {
  const color = STATUS_COLOR[status];
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
      animate={
        status === "active" && !reducedMotion
          ? { scale: [1, 1.03, 1] }
          : { scale: 1 }
      }
      transition={
        status === "active" && !reducedMotion
          ? { duration: 1.1, repeat: Infinity, ease: "easeInOut" }
          : { duration: 0.3, ease: "easeOut" }
      }
      role="status"
      aria-label={`${t(node.labelKey)} — ${t(`liveWorkflow.state.${status}`)}`}
    >
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

function Wire({ edge, status, reducedMotion }) {
  const from = NODE_BY_ID[edge.from];
  const to = NODE_BY_ID[edge.to];
  const { d } = edgeAnchors(from, to);
  const color = STATUS_COLOR[status];
  const pathId = `wire-${edge.id}`;
  return (
    <g>
      <path d={d} fill="none" stroke="rgba(255,255,255,0.10)" strokeWidth={1.5} />
      {status !== "idle" && (
        <path id={pathId} d={d} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" opacity={0.85} />
      )}
      {status === "active" && !reducedMotion && (
        <circle r={3.5} fill={color}>
          <animateMotion dur="1.15s" repeatCount="indefinite">
            <mpath xlinkHref={`#${pathId}`} />
          </animateMotion>
        </circle>
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

  const agentNode = NODE_BY_ID.agent;
  const caption = isLive
    ? currentLabel
    : t(`liveWorkflow.node.${keyOf(DEMO_SEQUENCE[Math.min(demoStep, DEMO_SEQUENCE.length - 1)])}`);

  return (
    <div className="flex h-full w-full flex-col">
      <div className="flex items-center justify-between px-4 pt-3 sm:px-5">
        <LiveIndicator isLive={isLive} t={t} />
        <p className="truncate pl-3 text-right font-mono text-[10px] text-slate-500 sm:text-[11px]">{caption}</p>
      </div>

      <div className="min-h-0 flex-1 overflow-x-auto overflow-y-hidden px-2 py-2 sm:px-4">
        <div className="relative mx-auto" style={{ width: CANVAS_W, height: CANVAS_H }}>
          <svg
            width={CANVAS_W}
            height={CANVAS_H}
            viewBox={`0 0 ${CANVAS_W} ${CANVAS_H}`}
            className="absolute inset-0"
            aria-hidden="true"
          >
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
    <div ref={containerRef} className="h-full w-full">
      {hasLoaded ? <WorkflowLive /> : <div className="h-full w-full" aria-hidden="true" />}
    </div>
  );
}
