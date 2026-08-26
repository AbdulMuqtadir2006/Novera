// Data source for the live 2D workflow diagram (components/home/LiveWorkflow).
// Node `id`s are a hard contract with the backend's WebSocket event stream
// (`/ws/pipeline`, see hooks/useWorkflowSocket.js) — they must match the
// `node` field of every event exactly. Do not rename without checking the
// backend's `whatsapp_agent.py` instrumentation stays in sync.
//
// MERGED 2026-08-20 (see novera-whatsapp-autonomous-agent-spec.md's
// successor doc, and backend/app/core/whatsapp_agent.py's module docstring):
// Guidance Agent no longer exists as a separate module — its 3 tools
// (run_screening_pipeline, generate_report, request_retest) were ported into
// WhatsApp Agent, which is now the single orchestrator for the whole system.
// This used to be two independent lanes (`source: "device"` for the old
// Guidance Agent, `source: "whatsapp"` for WhatsApp Agent) with a
// screening.completed hand-off between them; now it's one continuous flow —
// 5 triggers (including the new sensor.reading_received, replacing the old
// hand-off) feed one brain, which can call run_screening_pipeline (validate
// -> score KIDNEY/LIVER/ORAL, shown as the same forward chain the old
// lane 1 used) as one of its own tools, then decide what to do next from
// there — report, retest, book, message, or stay quiet — all in one run.
//
// Layout is a fixed pixel canvas (n8n-style: left-to-right flow, nodes as
// cards, curved wires) rather than percentage-based, so wires and node
// anchors line up exactly regardless of viewport — LiveWorkflowDiagram.jsx
// measures the real container width and applies a CSS `scale()` transform
// to this canvas instead of letting it overflow/scroll. The merge shrank
// the canvas substantially (1120 -> ~760 tall) since this is one lane now,
// not two stacked ones.
//
// TOOL PORT (added 2026-08-22): the 8 tool nodes below now visually route
// through TOOL_PORT_NODE, a synthetic circular hub sitting between wa_agent
// and the tool column — see TOOL_PORT_NODE/DISPLAY_NODE_BY_ID further down.
// It's deliberately NOT in WORKFLOW_NODES/NODE_BY_ID/ALL_NODE_IDS/
// RESETTABLE_NODE_IDS (the hard contract above is for real backend-emitting
// nodes only) — its status is derived client-side in LiveWorkflowDiagram.jsx
// from the real 8 tool statuses, never set directly from a socket event.
import {
  Wifi,
  ShieldCheck,
  Droplet,
  Utensils,
  Filter,
  Smile,
  MessageCircle,
  FileText,
  RotateCcw,
  Sparkles,
  Database,
  Wrench,
  CalendarCheck,
  HeartPulse,
  Send,
  Search,
  CalendarClock,
  Stethoscope,
  CheckCircle2,
  Repeat,
} from "lucide-react";

export const CANVAS_W = 1280;
// 760 -> 820 (2026-08-26): grew to make room for the retest-loop-back wire's
// bottom-margin routing segment (see RetestLoopWire in LiveWorkflowDiagram.jsx)
// below every real node's lowest edge (autonomousChain satellite bottoms out
// at y=695) without crowding it.
export const CANVAS_H = 820;

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
  // 5 triggers — the agent's 5 independent ways to wake up, only one of
  // which (the last) needs a patient to have done anything.
  { id: "wa_trigger_reading", labelKey: "liveWorkflow.node.waTriggerReading", icon: Wifi, x: 85, y: 155, w: 172, h: 54, group: "signal" },
  { id: "wa_trigger_appointment", labelKey: "liveWorkflow.node.waTriggerAppointment", icon: CalendarCheck, x: 85, y: 280, w: 172, h: 54, group: "signal" },
  { id: "wa_trigger_meal", labelKey: "liveWorkflow.node.waTriggerMeal", icon: Utensils, x: 85, y: 390, w: 172, h: 54, group: "signal" },
  { id: "wa_trigger_wellness", labelKey: "liveWorkflow.node.waTriggerWellness", icon: HeartPulse, x: 85, y: 500, w: 172, h: 54, group: "signal" },
  { id: "wa_trigger_message", labelKey: "liveWorkflow.node.waTriggerMessage", icon: Send, x: 85, y: 610, w: 172, h: 54, group: "signal" },

  // The screening sub-flow — only lit up on sensor.reading_received, when
  // the agent calls its own run_screening_pipeline tool. Deterministic
  // scoring math (scoring.py) is untouched by the merge; only who calls it
  // (the single agent, as a tool) changed.
  { id: "validate", labelKey: "liveWorkflow.node.validate", icon: ShieldCheck, x: 300, y: 155, w: 140, h: 56, group: "iris" },
  { id: "score_kidney", labelKey: "liveWorkflow.node.scoreKidney", icon: Droplet, x: 500, y: 75, w: 164, h: 56, group: "iris" },
  { id: "score_liver", labelKey: "liveWorkflow.node.scoreLiver", icon: Filter, x: 500, y: 155, w: 164, h: 56, group: "iris" },
  { id: "score_oral", labelKey: "liveWorkflow.node.scoreOral", icon: Smile, x: 500, y: 235, w: 164, h: 56, group: "iris" },

  // The single orchestrator — every trigger feeds it, it decides everything.
  { id: "wa_agent", labelKey: "liveWorkflow.node.waAgent", icon: MessageCircle, x: 750, y: 390, w: 230, h: 112, group: "vital" },

  // 8 tool groups it can reach for, fanned out on the right (bundled by
  // related tools, e.g. book/cancel/reschedule as one "Booking" node,
  // rather than showing all 16 individual tools).
  { id: "wa_tool_facts", labelKey: "liveWorkflow.node.waToolFacts", detailKey: "liveWorkflow.node.waToolFactsDetail", icon: Search, x: 1125, y: 128, w: 182, h: 54, group: "amber" },
  { id: "wa_tool_booking", labelKey: "liveWorkflow.node.waToolBooking", detailKey: "liveWorkflow.node.waToolBookingDetail", icon: CalendarClock, x: 1125, y: 203, w: 182, h: 54, group: "amber" },
  { id: "wa_tool_media", labelKey: "liveWorkflow.node.waToolMedia", detailKey: "liveWorkflow.node.waToolMediaDetail", icon: FileText, x: 1125, y: 278, w: 182, h: 54, group: "amber" },
  { id: "wa_tool_offer", labelKey: "liveWorkflow.node.waToolOffer", detailKey: "liveWorkflow.node.waToolOfferDetail", icon: Stethoscope, x: 1125, y: 353, w: 182, h: 54, group: "amber" },
  { id: "wa_tool_checkin", labelKey: "liveWorkflow.node.waToolCheckin", detailKey: "liveWorkflow.node.waToolCheckinDetail", icon: CheckCircle2, x: 1125, y: 428, w: 182, h: 54, group: "amber" },
  { id: "wa_tool_memory", labelKey: "liveWorkflow.node.waToolMemory", detailKey: "liveWorkflow.node.waToolMemoryDetail", icon: Database, x: 1125, y: 503, w: 182, h: 54, group: "amber" },
  { id: "wa_tool_report", labelKey: "liveWorkflow.node.toolReport", detailKey: "liveWorkflow.node.toolReportDetail", icon: FileText, x: 1125, y: 578, w: 182, h: 54, group: "amber" },
  { id: "wa_tool_retest", labelKey: "liveWorkflow.node.toolRetest", detailKey: "liveWorkflow.node.toolRetestDetail", icon: RotateCcw, x: 1125, y: 653, w: 182, h: 54, group: "amber" },
];

export const NODE_BY_ID = Object.fromEntries(WORKFLOW_NODES.map((n) => [n.id, n]));

// Synthetic, frontend-only hub the 8 tool nodes visually route through —
// see the TOOL PORT comment above. Not a WORKFLOW_NODES member on purpose:
// it never receives a real backend event, so it must stay out of every
// array that models "a real node the socket can address."
export const TOOL_PORT_NODE = {
  id: "wa_tool_port",
  labelKey: "liveWorkflow.satellite.tool",
  detailKey: "liveWorkflow.satellite.toolDetail",
  icon: Wrench,
  x: 945,
  y: 390,
  w: 104,
  h: 104,
};

// The one place code that needs to resolve BOTH real nodes and the display-
// only port by id should look things up (edge anchors, the sr-only paragraph
// in AgentFlowSection.jsx) — NODE_BY_ID itself stays exactly what it always
// was, the hard-contract map of real nodes only.
export const DISPLAY_NODE_BY_ID = { ...NODE_BY_ID, [TOOL_PORT_NODE.id]: TOOL_PORT_NODE };

export const WHATSAPP_TRIGGER_NODE_IDS = [
  "wa_trigger_reading",
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
  "wa_tool_report",
  "wa_tool_retest",
];
// validate/score_* only ever light up mid-run (inside run_screening_pipeline)
// but still need to reset to idle at the start of every new trigger, same as
// the tool nodes — otherwise a leftover "success" from a past reading trigger
// would still be showing when e.g. a meal check-in trigger fires next.
export const SCREENING_SUBSTEP_NODE_IDS = ["validate", "score_kidney", "score_liver", "score_oral"];
// Every node except the brain itself — what useWorkflowSocket resets to idle
// whenever a new trigger starts.
export const RESETTABLE_NODE_IDS = [...WHATSAPP_TRIGGER_NODE_IDS, ...SCREENING_SUBSTEP_NODE_IDS, ...WHATSAPP_TOOL_NODE_IDS];

export const ALL_NODE_IDS = WORKFLOW_NODES.map((n) => n.id);

// Solid wires — each animates off the real event stream.
export const WORKFLOW_EDGES = [
  { id: "reading-validate", from: "wa_trigger_reading", to: "validate" },
  { id: "validate-kidney", from: "validate", to: "score_kidney" },
  { id: "validate-liver", from: "validate", to: "score_liver" },
  { id: "validate-oral", from: "validate", to: "score_oral" },
  { id: "kidney-agent", from: "score_kidney", to: "wa_agent" },
  { id: "liver-agent", from: "score_liver", to: "wa_agent" },
  { id: "oral-agent", from: "score_oral", to: "wa_agent" },

  { id: "wa-appointment-agent", from: "wa_trigger_appointment", to: "wa_agent" },
  { id: "wa-meal-agent", from: "wa_trigger_meal", to: "wa_agent" },
  { id: "wa-wellness-agent", from: "wa_trigger_wellness", to: "wa_agent" },
  { id: "wa-message-agent", from: "wa_trigger_message", to: "wa_agent" },

  // Routed through the tool port (added 2026-08-22), not straight off
  // wa_agent — `optional: true` on all 9 of these means edgeDisplayStatus
  // only lights them up on a real per-tool event, never just because
  // wa_agent itself succeeded (see edgeDisplayStatus's own comment in
  // LiveWorkflowDiagram.jsx for why that distinction matters here).
  { id: "wa-agent-toolport", from: "wa_agent", to: "wa_tool_port", optional: true },
  { id: "toolport-facts", from: "wa_tool_port", to: "wa_tool_facts", optional: true },
  { id: "toolport-booking", from: "wa_tool_port", to: "wa_tool_booking", optional: true },
  { id: "toolport-media", from: "wa_tool_port", to: "wa_tool_media", optional: true },
  { id: "toolport-offer", from: "wa_tool_port", to: "wa_tool_offer", optional: true },
  { id: "toolport-checkin", from: "wa_tool_port", to: "wa_tool_checkin", optional: true },
  { id: "toolport-memory", from: "wa_tool_port", to: "wa_tool_memory", optional: true },
  { id: "toolport-report", from: "wa_tool_port", to: "wa_tool_report", optional: true },
  { id: "toolport-retest", from: "wa_tool_port", to: "wa_tool_retest", optional: true },
];

// Static decorative satellites hanging off the agent node (dashed lines, no
// event coverage — mirrors the reference n8n screenshot's Chat
// Model/Memory/Tool trio under its "AI Agent" node). dx/dy are offsets from
// the agent node's own center. The "Tool" third of the trio graduated
// (2026-08-22) into TOOL_PORT_NODE above — a real, live-status hub instead
// of a decorative chip, since unlike chat-model/memory it has 8 real,
// per-event nodes to actually represent. Re-centered as a pair now that
// there are 2, not 3.
export const AGENT_SATELLITES = [
  { id: "chatModel", labelKey: "liveWorkflow.satellite.chatModel", detailKey: "liveWorkflow.satellite.chatModelDetail", icon: Sparkles, dx: -75, dy: 150 },
  { id: "memory", labelKey: "liveWorkflow.satellite.memory", detailKey: "liveWorkflow.satellite.memoryDetail", icon: Database, dx: 75, dy: 150 },
  // Decorative, same non-event-driven pattern as the two above — grounded in
  // real behavior (2026-08-26), not illustrative fiction: within one
  // sensor.reading_received run, the agent can call run_screening_pipeline
  // and then, based on what it returns, autonomously chain straight into
  // request_retest (validation failed / low confidence) or
  // generate_report + send_appointment_offer (a confident flagged result) —
  // no human approves the step in between. Centered below the other two
  // (dx: 0) rather than beside them — placed further down (dy: 260 vs
  // their 150) so its chip clears both without overlapping (checked against
  // WORKFLOW_NODES' fixed coordinates: nearest real nodes are wa_trigger_
  // wellness/wa_trigger_message at x=85, far outside this chip's ~x:[684,816]
  // span, and wa_tool_checkin at y=428, well above this chip's y:[605,695]).
  { id: "autonomousChain", labelKey: "liveWorkflow.satellite.autonomousChain", detailKey: "liveWorkflow.satellite.autonomousChainDetail", icon: Repeat, dx: 0, dy: 260 },
];

// Illustrative loop for the always-alive idle/preview animation (no backend
// connection yet, or none seen in a while) — walks the whole merged system
// end to end: a reading arrives, gets screened, and the same agent decides
// to offer an appointment, telling the real one-brain story a visitor would
// otherwise only see mid-way through an actual live run.
export const DEMO_SEQUENCE = [
  "wa_trigger_reading",
  "validate",
  "score_kidney",
  "score_liver",
  "score_oral",
  "wa_agent",
  "wa_tool_report",
  "wa_tool_offer",
];
