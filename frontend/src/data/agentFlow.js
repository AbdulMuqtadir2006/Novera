// Data source for the 3D agent-flow visualization (components/home/AgentFlow3D).
// Deliberately separate from data/agents.js (which drives the flat card grid in
// AgentsSection) — this shape is graph-oriented (nodes + directed edges) so it
// can plug into a live event feed later without reshaping the card copy.
//
// Topology mirrors the real backend pipeline (backend/app/core/whatsapp_agent.py,
// appointment_graph.py, i18n `appt.pipelineHint`): a linear chain
// (capture -> analysis -> insight) hands off to guidance, which acts as the
// dispatcher/manager — it fans out to the three agents that actually produce
// user-facing output: voice, report, and (conditionally, only when a clinical
// threshold is crossed) whatsapp.

// Brand gradient walk (tailwind.config.js): signal (cyan) -> iris (purple) ->
// vital (magenta), same 3 stops used by VoiceOrb.jsx's aurora core. Amber is
// tailwind's `status.watch` token, reused here to mark the WhatsApp path as
// conditional/escalation rather than part of the always-runs chain.
export const FLOW_COLORS = {
  signal: "#28CFE0",
  iris: "#B24BD6",
  vital: "#EC61E8",
  amber: "#F2A93E",
};

// role: "manager" gets distinct visual treatment (bigger, halo ring, badge)
// in Scene.jsx — this is the one node that both receives from the chain and
// dispatches to the output agents, i.e. the orchestrator.
export const agentFlowNodes = [
  { id: "capture", label: "Capture", detail: "Reads the raw signal", color: FLOW_COLORS.signal, role: "agent" },
  { id: "analysis", label: "Analysis", detail: "Scores against reference models", color: FLOW_COLORS.signal, role: "agent" },
  { id: "insight", label: "Insight", detail: "Plain-language read", color: FLOW_COLORS.iris, role: "agent" },
  { id: "guidance", label: "Guidance", detail: "Manager — decides & dispatches", color: FLOW_COLORS.iris, role: "manager" },
  { id: "voice", label: "Voice Agent", detail: "Spoken summary", color: FLOW_COLORS.vital, role: "agent" },
  { id: "report", label: "Report Agent", detail: "Written record", color: FLOW_COLORS.vital, role: "agent" },
  { id: "whatsapp", label: "WhatsApp Agent", detail: "Escalates over threshold", color: FLOW_COLORS.amber, role: "agent" },
];

// speed: full arc traversals per second for the ambient pulse on that edge.
// status: "active" pulses continuously (runs on every reading); "idle" sits
// as a dim static line until fireEvent(edgeId) is called — used here for the
// WhatsApp edge, which is genuinely conditional in the real pipeline (only
// fires when a clinical threshold is crossed), not just a styling choice.
export const agentFlowEdges = [
  { id: "capture-analysis", from: "capture", to: "analysis", color: FLOW_COLORS.signal, speed: 0.35, status: "active" },
  { id: "analysis-insight", from: "analysis", to: "insight", color: FLOW_COLORS.signal, speed: 0.3, status: "active" },
  { id: "insight-guidance", from: "insight", to: "guidance", color: FLOW_COLORS.iris, speed: 0.3, status: "active" },
  { id: "guidance-voice", from: "guidance", to: "voice", color: FLOW_COLORS.vital, speed: 0.25, status: "active" },
  { id: "guidance-report", from: "guidance", to: "report", color: FLOW_COLORS.vital, speed: 0.22, status: "active" },
  { id: "guidance-whatsapp", from: "guidance", to: "whatsapp", color: FLOW_COLORS.amber, speed: 0.4, status: "idle" },
];
