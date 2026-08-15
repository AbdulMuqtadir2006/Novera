// Data source for the live 2D workflow diagram (components/home/LiveWorkflow).
// Node `id`s are a hard contract with the backend's WebSocket event stream
// (`/ws/pipeline`, see hooks/useWorkflowSocket.js) — they must match the
// `node` field of every event exactly. Do not rename without checking the
// backend's `whatsapp_agent.py` / pipeline instrumentation stays in sync.
//
// Layout is a fixed pixel canvas (n8n-style: left-to-right flow, nodes as
// cards, curved wires) rather than percentage-based, so wires and node
// anchors line up exactly regardless of viewport — LiveWorkflowDiagram.jsx
// measures the real container width and applies a CSS `scale()` transform
// to this canvas instead of letting it overflow/scroll. Column gaps below
// are intentionally tight (only as wide as each pair of node half-widths
// needs, plus a small margin) — every px trimmed from CANVAS_W raises the
// effective scale (and therefore legibility) at every viewport width.
import {
  Wifi,
  ShieldCheck,
  Droplet,
  Utensils,
  Smile,
  Bot,
  FileText,
  Mic,
  HeartPulse,
  MessageCircle,
  RotateCcw,
  Sparkles,
  Database,
  Wrench,
} from "lucide-react";

export const CANVAS_W = 1000;
export const CANVAS_H = 520;

// x/y = card center. Widths are sized generously against the actual longest
// label per node ("Self-Care Plan", "Request Retest", "Sensor Reading" —
// 12-14 chars at 12-13px font-body-semibold plus the icon/badge/padding
// chrome) so `truncate` in NodeCard is a safety net, not the default
// behavior — a demo diagram reading "Kidn…" in front of judges is worse
// than a slightly wider canvas.
//
// Groups drive the idle "brand color" used by the legend dot and the node's
// baseline accent — independent of live run status, which is layered on top
// (see STATUS_STYLE in LiveWorkflowDiagram.jsx).
export const WORKFLOW_NODES = [
  { id: "device", labelKey: "liveWorkflow.node.device", icon: Wifi, x: 85, y: 260, w: 150, h: 64, group: "signal" },
  { id: "validate", labelKey: "liveWorkflow.node.validate", icon: ShieldCheck, x: 260, y: 260, w: 140, h: 64, group: "signal" },

  { id: "score_kidney", labelKey: "liveWorkflow.node.scoreKidney", icon: Droplet, x: 440, y: 85, w: 164, h: 60, group: "iris" },
  { id: "score_stomach", labelKey: "liveWorkflow.node.scoreStomach", icon: Utensils, x: 440, y: 260, w: 164, h: 60, group: "iris" },
  { id: "score_oral", labelKey: "liveWorkflow.node.scoreOral", icon: Smile, x: 440, y: 435, w: 164, h: 60, group: "iris" },

  { id: "agent", labelKey: "liveWorkflow.node.agent", icon: Bot, x: 660, y: 260, w: 210, h: 108, group: "vital" },

  { id: "tool_report", labelKey: "liveWorkflow.node.toolReport", icon: FileText, x: 885, y: 45, w: 172, h: 58, group: "amber" },
  { id: "tool_voice", labelKey: "liveWorkflow.node.toolVoice", icon: Mic, x: 885, y: 152, w: 172, h: 58, group: "amber" },
  { id: "tool_selfcare", labelKey: "liveWorkflow.node.toolSelfcare", icon: HeartPulse, x: 885, y: 260, w: 172, h: 58, group: "amber" },
  { id: "tool_whatsapp", labelKey: "liveWorkflow.node.toolWhatsapp", icon: MessageCircle, x: 885, y: 368, w: 172, h: 58, group: "amber" },
  { id: "tool_retest", labelKey: "liveWorkflow.node.toolRetest", icon: RotateCcw, x: 885, y: 475, w: 172, h: 58, group: "amber" },
];

export const NODE_BY_ID = Object.fromEntries(WORKFLOW_NODES.map((n) => [n.id, n]));

// The 5 tool nodes are the only ones that may legitimately sit out a run
// (the agent decides which to invoke) — this is the list the socket hook
// resets to "idle" at the start of every new run.
export const TOOL_NODE_IDS = ["tool_report", "tool_voice", "tool_selfcare", "tool_whatsapp", "tool_retest"];

export const ALL_NODE_IDS = WORKFLOW_NODES.map((n) => n.id);

// Solid wires — each animates off the real event stream.
export const WORKFLOW_EDGES = [
  { id: "device-validate", from: "device", to: "validate" },
  { id: "validate-kidney", from: "validate", to: "score_kidney" },
  { id: "validate-stomach", from: "validate", to: "score_stomach" },
  { id: "validate-oral", from: "validate", to: "score_oral" },
  { id: "kidney-agent", from: "score_kidney", to: "agent" },
  { id: "stomach-agent", from: "score_stomach", to: "agent" },
  { id: "oral-agent", from: "score_oral", to: "agent" },
  { id: "agent-report", from: "agent", to: "tool_report" },
  { id: "agent-voice", from: "agent", to: "tool_voice" },
  { id: "agent-selfcare", from: "agent", to: "tool_selfcare" },
  { id: "agent-whatsapp", from: "agent", to: "tool_whatsapp" },
  { id: "agent-retest", from: "agent", to: "tool_retest" },
];

// Static decorative satellites hanging off the AI Agent node (dashed lines,
// no event coverage — mirrors the reference n8n screenshot's Chat
// Model/Memory/Tool trio under its "AI Agent" node). dx/dy are offsets from
// the agent node's own center.
export const AGENT_SATELLITES = [
  { id: "chatModel", labelKey: "liveWorkflow.satellite.chatModel", detailKey: "liveWorkflow.satellite.chatModelDetail", icon: Sparkles, dx: -140, dy: 98 },
  { id: "memory", labelKey: "liveWorkflow.satellite.memory", detailKey: "liveWorkflow.satellite.memoryDetail", icon: Database, dx: 0, dy: 98 },
  { id: "tool", labelKey: "liveWorkflow.satellite.tool", detailKey: "liveWorkflow.satellite.toolDetail", icon: Wrench, dx: 140, dy: 98 },
];

// Illustrative loop for the always-alive idle/preview animation (no backend
// connection yet, or none seen in a while). Deliberately skips two tool
// nodes each pass, like a real run would, so the preview still reads as
// "the agent is choosing" rather than "everything always fires."
export const DEMO_SEQUENCE = [
  "device",
  "validate",
  "score_kidney",
  "score_stomach",
  "score_oral",
  "agent",
  "tool_voice",
  "tool_report",
  "tool_selfcare",
];
