import { Radar, GitCompareArrows, MessageSquareText, Compass } from "lucide-react";

// The one agent's 4 phases (brief §4.3, structure mirrors the app's tabs) —
// renamed 2026-08-22 from 4 separate "Agent" cards (Capture/Analysis/
// Insight/Guidance Agent) to phases of the same agent. That framing was
// stale: "Guidance Agent" hasn't existed as a standalone module since the
// 2026-08-20 orchestrator merge (see backend/app/core/whatsapp_agent.py),
// and AgentsSection sits directly above AgentFlowSection's "One agent.
// Every decision." — a visitor was reading the opposite story twice in a
// row. `copy` is untouched; it was already accurate, just mislabeled.
export const agents = [
  {
    id: "capture",
    name: "Capture",
    icon: Radar,
    copy: "Reads the raw biomarker signal the moment your sample hits the sensor.",
  },
  {
    id: "analysis",
    name: "Analysis",
    icon: GitCompareArrows,
    copy: "Cross-references pH, creatinine, urea, and temperature against Novera's four screening models.",
  },
  {
    id: "insight",
    name: "Insight",
    icon: MessageSquareText,
    copy: "Turns the analysis into plain language and flags anything worth a closer look.",
  },
  {
    id: "guidance",
    name: "Guidance",
    icon: Compass,
    copy: "Builds your next steps — natural recovery suggestions, your spoken summary, your report.",
  },
];
