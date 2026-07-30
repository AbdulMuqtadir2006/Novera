import { Radar, GitCompareArrows, MessageSquareText, Compass } from "lucide-react";

// The agent pipeline (brief §4.3). Structure mirrors the app's tabs.
export const agents = [
  {
    id: "capture",
    name: "Capture Agent",
    icon: Radar,
    copy: "Reads the raw biomarker signal the moment your sample hits the sensor.",
  },
  {
    id: "analysis",
    name: "Analysis Agent",
    icon: GitCompareArrows,
    copy: "Cross-references pH, creatinine, urea, and temperature against Novera's four screening models.",
  },
  {
    id: "insight",
    name: "Insight Agent",
    icon: MessageSquareText,
    copy: "Turns the analysis into plain language and flags anything worth a closer look.",
  },
  {
    id: "guidance",
    name: "Guidance Agent",
    icon: Compass,
    copy: "Builds your next steps — self-care suggestions, your spoken summary, your report.",
  },
];
