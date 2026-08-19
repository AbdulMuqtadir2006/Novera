// Data source for the live 2D workflow diagram (components/home/LiveWorkflow).
// Node `id`s are a hard contract with the backend's WebSocket event stream
// (`/ws/pipeline`, see hooks/useWorkflowSocket.js) — they must match the
// `node` field of every event exactly. Do not rename without checking the
// backend's `guidance_agent.py` / pipeline instrumentation stays in sync.
//
// Scope note (2026-08-19, see novera-whatsapp-autonomous-agent-spec.md):
// Guidance Agent's job narrowed to validate -> score -> decide -> report |
// request_retest — voice/self-care/appointment-offer tools moved to the
// autonomous WhatsApp Agent (lane 2 below). Lane 1 (Guidance Agent, top) and
// lane 2 (WhatsApp Agent, bottom) are visually and logically independent —
// see useWorkflowSocket.js, which branches on each event's `source` field
// ("device" for lane 1, "whatsapp" for lane 2) so a run in one lane never
// resets or lights up nodes in the other.
//
// Layout is a fixed pixel canvas (n8n-style: left-to-right flow, nodes as
// cards, curved wires) rather than percentage-based, so wires and node
// anchors line up exactly regardless of viewport — LiveWorkflowDiagram.jsx
// measures the real container width and applies a CSS `scale()` transform
// to this canvas instead of letting it overflow/scroll. Column gaps below
// are deliberately generous (well beyond each pair of node half-widths) so
// wires have visible curve and columns don't read as stacked/congested on
// wide desktop viewports — CANVAS_W is kept in the 1200-1280 range rather
// than wider still so scale-down legibility on narrow/mobile viewports
// doesn't regress.
import {
  Wifi,
  ShieldCheck,
  Droplet,
  Utensils,
  Smile,
  Bot,
  FileText,
  RotateCcw,
  Sparkles,
  Database,
  Wrench,
  ClipboardCheck,
  CalendarCheck,
  HeartPulse,
  Send,
  MessageCircle,
  Search,
  CalendarClock,
  Stethoscope,
  CheckCircle2,
} from "lucide-react";

export const CANVAS_W = 1240;
export const CANVAS_H = 1120;

// Lane 2 (WhatsApp Agent) node y-positions are centered on 850 — 5 triggers
// at an 80px pitch, 6 tool groups at a 75px pitch, wa_agent itself at 850 —
// see WORKFLOW_NODES below.

// x/y = card center. Widths are sized generously against the actual longest
// label per node ("Natural Recovery", "Request Retest", "Sensor Reading" —
// 12-14 chars at 12-13px font-body-semibold plus the icon/badge/padding
// chrome) so `truncate` in NodeCard is a safety net, not the default
// behavior — a demo diagram reading "Kidn…" in front of judges is worse
// than a slightly wider canvas.
//
// Groups drive the idle "brand color" used by the legend dot and the node's
// baseline accent — independent of live run status, which is layered on top
// (see STATUS_STYLE in LiveWorkflowDiagram.jsx).
export const WORKFLOW_NODES = [
  { id: "device", labelKey: "liveWorkflow.node.device", icon: Wifi, x: 85, y: 280, w: 150, h: 64, group: "signal" },
  { id: "validate", labelKey: "liveWorkflow.node.validate", icon: ShieldCheck, x: 260, y: 280, w: 140, h: 64, group: "signal" },

  { id: "score_kidney", labelKey: "liveWorkflow.node.scoreKidney", icon: Droplet, x: 520, y: 85, w: 164, h: 60, group: "iris" },
  { id: "score_stomach", labelKey: "liveWorkflow.node.scoreStomach", icon: Utensils, x: 520, y: 280, w: 164, h: 60, group: "iris" },
  { id: "score_oral", labelKey: "liveWorkflow.node.scoreOral", icon: Smile, x: 520, y: 475, w: 164, h: 60, group: "iris" },

  { id: "agent", labelKey: "liveWorkflow.node.agent", icon: Bot, x: 820, y: 280, w: 210, h: 108, group: "vital" },

  // Only 2 tool nodes now (down from 5) — voice/self-care/appointment-offer
  // moved to the WhatsApp Agent lane (not visualized here yet, see header
  // note). Repositioned to flank the agent's vertical center (280) rather
  // than leaving the original 5-node vertical spread with 3 empty gaps.
  { id: "tool_report", labelKey: "liveWorkflow.node.toolReport", icon: FileText, x: 1125, y: 200, w: 172, h: 58, group: "amber" },
  { id: "tool_retest", labelKey: "liveWorkflow.node.toolRetest", icon: RotateCcw, x: 1125, y: 360, w: 172, h: 58, group: "amber" },

  // --- Lane 2: WhatsApp Agent — autonomous, 5 triggers -> 1 brain -> 6 tool
  // groups (grouped per the spec's own §1 diagram: G1..G6 bundle related
  // tools, e.g. book/cancel/reschedule as one "Booking" node, rather than
  // showing all 12 individual tools — same abstraction level lane 1 already
  // uses for its own internal steps). `waGroup` (not `group`) drives idle
  // color so this lane reads as visually distinct from lane 1 at a glance.
  { id: "wa_trigger_screening", labelKey: "liveWorkflow.node.waTriggerScreening", icon: ClipboardCheck, x: 85, y: 690, w: 172, h: 54, group: "signal", waGroup: true },
  { id: "wa_trigger_appointment", labelKey: "liveWorkflow.node.waTriggerAppointment", icon: CalendarCheck, x: 85, y: 770, w: 172, h: 54, group: "signal", waGroup: true },
  { id: "wa_trigger_meal", labelKey: "liveWorkflow.node.waTriggerMeal", icon: Utensils, x: 85, y: 850, w: 172, h: 54, group: "signal", waGroup: true },
  { id: "wa_trigger_wellness", labelKey: "liveWorkflow.node.waTriggerWellness", icon: HeartPulse, x: 85, y: 930, w: 172, h: 54, group: "signal", waGroup: true },
  { id: "wa_trigger_message", labelKey: "liveWorkflow.node.waTriggerMessage", icon: Send, x: 85, y: 1010, w: 172, h: 54, group: "signal", waGroup: true },

  { id: "wa_agent", labelKey: "liveWorkflow.node.waAgent", icon: MessageCircle, x: 650, y: 850, w: 220, h: 100, group: "vital", waGroup: true },

  { id: "wa_tool_facts", labelKey: "liveWorkflow.node.waToolFacts", icon: Search, x: 1125, y: 663, w: 182, h: 54, group: "amber", waGroup: true },
  { id: "wa_tool_booking", labelKey: "liveWorkflow.node.waToolBooking", icon: CalendarClock, x: 1125, y: 738, w: 182, h: 54, group: "amber", waGroup: true },
  { id: "wa_tool_media", labelKey: "liveWorkflow.node.waToolMedia", icon: FileText, x: 1125, y: 813, w: 182, h: 54, group: "amber", waGroup: true },
  { id: "wa_tool_offer", labelKey: "liveWorkflow.node.waToolOffer", icon: Stethoscope, x: 1125, y: 888, w: 182, h: 54, group: "amber", waGroup: true },
  { id: "wa_tool_checkin", labelKey: "liveWorkflow.node.waToolCheckin", icon: CheckCircle2, x: 1125, y: 963, w: 182, h: 54, group: "amber", waGroup: true },
  { id: "wa_tool_memory", labelKey: "liveWorkflow.node.waToolMemory", icon: Database, x: 1125, y: 1038, w: 182, h: 54, group: "amber", waGroup: true },
];

export const NODE_BY_ID = Object.fromEntries(WORKFLOW_NODES.map((n) => [n.id, n]));

// The 2 tool nodes are the only ones that may legitimately sit out a run
// (the agent decides which to invoke) — this is the list the socket hook
// resets to "idle" at the start of every new lane-1 run. Lane-2 (WhatsApp)
// nodes are deliberately excluded — see WHATSAPP_* lists below, reset
// independently so a lane-1 run never disturbs lane-2 state and vice versa.
export const TOOL_NODE_IDS = ["tool_report", "tool_retest"];

export const WHATSAPP_TRIGGER_NODE_IDS = [
  "wa_trigger_screening",
  "wa_trigger_appointment",
  "wa_trigger_meal",
  "wa_trigger_wellness",
  "wa_trigger_message",
];
export const WHATSAPP_TOOL_NODE_IDS = [
  "wa_tool_facts",
  "wa_tool_booking",
  "wa_tool_media",
  "wa_tool_offer",
  "wa_tool_checkin",
  "wa_tool_memory",
];
// Every lane-2 node except the brain itself — what useWorkflowSocket resets
// to idle when a new whatsapp trigger fires, mirroring how lane-1's
// run_start resets TOOL_NODE_IDS.
export const WHATSAPP_RESETTABLE_NODE_IDS = [...WHATSAPP_TRIGGER_NODE_IDS, ...WHATSAPP_TOOL_NODE_IDS];

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
  { id: "agent-retest", from: "agent", to: "tool_retest" },

  // Lane 2 — 5 triggers feed straight into the WhatsApp Agent brain (no
  // intermediate validate/score step, unlike lane 1), which fans out to 6
  // tool-group nodes.
  { id: "wa-screening-agent", from: "wa_trigger_screening", to: "wa_agent" },
  { id: "wa-appointment-agent", from: "wa_trigger_appointment", to: "wa_agent" },
  { id: "wa-meal-agent", from: "wa_trigger_meal", to: "wa_agent" },
  { id: "wa-wellness-agent", from: "wa_trigger_wellness", to: "wa_agent" },
  { id: "wa-message-agent", from: "wa_trigger_message", to: "wa_agent" },
  { id: "wa-agent-facts", from: "wa_agent", to: "wa_tool_facts" },
  { id: "wa-agent-booking", from: "wa_agent", to: "wa_tool_booking" },
  { id: "wa-agent-media", from: "wa_agent", to: "wa_tool_media" },
  { id: "wa-agent-offer", from: "wa_agent", to: "wa_tool_offer" },
  { id: "wa-agent-checkin", from: "wa_agent", to: "wa_tool_checkin" },
  { id: "wa-agent-memory", from: "wa_agent", to: "wa_tool_memory" },
];

// Static decorative satellites hanging off the AI Agent node (dashed lines,
// no event coverage — mirrors the reference n8n screenshot's Chat
// Model/Memory/Tool trio under its "AI Agent" node). dx/dy are offsets from
// the agent node's own center.
export const AGENT_SATELLITES = [
  { id: "chatModel", labelKey: "liveWorkflow.satellite.chatModel", detailKey: "liveWorkflow.satellite.chatModelDetail", icon: Sparkles, dx: -120, dy: 150 },
  { id: "memory", labelKey: "liveWorkflow.satellite.memory", detailKey: "liveWorkflow.satellite.memoryDetail", icon: Database, dx: 0, dy: 150 },
  { id: "tool", labelKey: "liveWorkflow.satellite.tool", detailKey: "liveWorkflow.satellite.toolDetail", icon: Wrench, dx: 120, dy: 150 },
];

// Illustrative loop for the always-alive idle/preview animation (no backend
// connection yet, or none seen in a while). Now walks the *whole* system,
// not just lane 1 — lane 1 completing with a report flows straight into
// lane 2's real hand-off trigger (screening.completed) and one representative
// tool group, telling the actual end-to-end story a visitor would otherwise
// only see across two separate live runs.
export const DEMO_SEQUENCE = [
  "device",
  "validate",
  "score_kidney",
  "score_stomach",
  "score_oral",
  "agent",
  "tool_report",
  "wa_trigger_screening",
  "wa_agent",
  "wa_tool_offer",
];
