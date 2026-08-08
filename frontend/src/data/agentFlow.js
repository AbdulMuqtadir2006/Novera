// Data source for the 3D agent-flow visualization (components/home/AgentFlow3D).
// Deliberately separate from data/agents.js (which drives the flat card grid in
// AgentsSection) — this shape is graph-oriented (nodes + directed edges) so it
// can plug into a live event feed later without reshaping the card copy.
//
// Nodes mirror the four AgentsSection cards (capture/analysis/insight/guidance)
// plus the two terminal outputs already named in the existing pipeline copy
// (i18n `appt.pipelineHint`: "QA → analysis → insight → guidance → voice →
// report"), so the diagram matches language already live on the site instead
// of inventing new agent names.

// Brand gradient walk (tailwind.config.js): signal (cyan) -> iris (purple) ->
// vital (magenta), same 3 stops used by VoiceOrb.jsx's aurora core.
export const FLOW_COLORS = {
  signal: "#28CFE0",
  iris: "#B24BD6",
  vital: "#EC61E8",
};

export const agentFlowNodes = [
  { id: "capture", label: "Capture", detail: "Reads the raw signal", color: FLOW_COLORS.signal },
  { id: "analysis", label: "Analysis", detail: "Scores against reference models", color: FLOW_COLORS.signal },
  { id: "insight", label: "Insight", detail: "Plain-language read", color: FLOW_COLORS.iris },
  { id: "guidance", label: "Guidance", detail: "Decides next steps", color: FLOW_COLORS.iris },
  { id: "voice", label: "Voice", detail: "Spoken summary", color: FLOW_COLORS.vital },
  { id: "report", label: "Report", detail: "Written record", color: FLOW_COLORS.vital },
];

// speed: full arc traversals per second for the ambient pulse on that edge.
// status: "active" pulses continuously; "idle" sits dim until fireEvent() is
// called for it (kept for future use — every edge is "active" today so the
// scene reads as alive by default per the "should feel alive/ambient" brief).
export const agentFlowEdges = [
  { id: "capture-analysis", from: "capture", to: "analysis", color: FLOW_COLORS.signal, speed: 0.35, status: "active" },
  { id: "analysis-insight", from: "analysis", to: "insight", color: FLOW_COLORS.signal, speed: 0.3, status: "active" },
  { id: "insight-guidance", from: "insight", to: "guidance", color: FLOW_COLORS.iris, speed: 0.3, status: "active" },
  { id: "guidance-voice", from: "guidance", to: "voice", color: FLOW_COLORS.vital, speed: 0.25, status: "active" },
  { id: "guidance-report", from: "guidance", to: "report", color: FLOW_COLORS.vital, speed: 0.22, status: "active" },
];
