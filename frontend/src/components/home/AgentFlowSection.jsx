import { Section } from "./Section";
import { LiveWorkflowDiagram } from "./LiveWorkflow";
import { useLang } from "../../i18n/LanguageContext";
import { WORKFLOW_NODES, WORKFLOW_EDGES, DISPLAY_NODE_BY_ID } from "../../data/liveWorkflow";

const GROUP_DOT = {
  signal: "#28CFE0",
  iris: "#B24BD6",
  vital: "#EC61E8",
  amber: "#F2A93E",
};

// Same 4 groups the canvas already colors nodes by — the legend now clusters
// by them explicitly (with a small group label) instead of one flat row of
// pills, so it reads as a key to the diagram's structure rather than an
// afterthought caption underneath it.
const GROUP_ORDER = [
  { key: "signal", labelKey: "liveWorkflow.legend.input" },
  { key: "iris", labelKey: "liveWorkflow.legend.scores" },
  { key: "vital", labelKey: "liveWorkflow.legend.orchestrator" },
  { key: "amber", labelKey: "liveWorkflow.legend.actions" },
];

export function AgentFlowSection() {
  const { t } = useLang();

  return (
    <Section
      id="agent-flow"
      eyebrow="Live Under the Hood"
      title="One agent. Every decision. Live."
      intro="Every reading, message, and check-in runs through NOVERA's single orchestrator — the same agent screens a sample, writes the report, books the follow-up, and reaches out on WhatsApp, deciding for itself what's actually needed and when. Nothing here is scripted: this is that agent's real event stream, rendered live."
    >
      <div className="glass-card relative overflow-hidden">
        <div
          className="pointer-events-none absolute inset-0 grid-lines opacity-30"
          aria-hidden="true"
        />
        <LiveWorkflowDiagram />

        {/* Accessible text alternative — canvas/SVG pixels aren't readable by
            assistive tech, so the same pipeline is spelled out here. */}
        <p className="sr-only">
          {t("liveWorkflow.srIntro")} {WORKFLOW_NODES.map((n) => t(n.labelKey)).join(" → ")}.{" "}
          {t("liveWorkflow.srEdges")}{" "}
          {WORKFLOW_EDGES
            .map((e) => `${t(DISPLAY_NODE_BY_ID[e.from].labelKey)} to ${t(DISPLAY_NODE_BY_ID[e.to].labelKey)}`)
            .join(", ")}
          . {t("liveWorkflow.srToolNote")} {t("liveWorkflow.srToolPortNote")}
        </p>
      </div>

      {/* Visible legend — doubles as the fallback's own note for sighted
          users who want the labels spelled out even with the live view up.
          Clustered by the same 4 groups the canvas colors nodes by, each
          with its own mono label, inside one bordered strip so it reads as
          a key to the diagram rather than a loose row of chips underneath it. */}
      <div
        className="mt-6 flex flex-wrap items-center justify-center gap-x-4 gap-y-3 rounded-2xl border border-white/10 bg-white/[0.02] p-3 sm:p-4"
        aria-hidden="true"
      >
        {GROUP_ORDER.map((group, i) => {
          const nodes = WORKFLOW_NODES.filter((n) => n.group === group.key);
          const color = GROUP_DOT[group.key];
          return (
            <div key={group.key} className="flex flex-wrap items-center gap-1.5">
              {i > 0 && <span className="me-2.5 hidden h-5 w-px bg-white/10 sm:block" aria-hidden="true" />}
              <span
                className="me-0.5 font-mono text-[9.5px] font-medium uppercase tracking-[0.18em]"
                style={{ color: `${color}cc` }}
              >
                {t(group.labelKey)}
              </span>
              {nodes.map((node) => (
                <span
                  key={node.id}
                  className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 font-mono text-xs text-slate-300"
                >
                  <span
                    className="h-1.5 w-1.5 rounded-full"
                    style={{ backgroundColor: color, boxShadow: `0 0 8px ${color}` }}
                  />
                  {t(node.labelKey)}
                </span>
              ))}
            </div>
          );
        })}
      </div>
    </Section>
  );
}
