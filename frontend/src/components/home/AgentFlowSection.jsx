import { Section } from "./Section";
import { LiveWorkflowDiagram } from "./LiveWorkflow";
import { useLang } from "../../i18n/LanguageContext";
import { WORKFLOW_NODES, WORKFLOW_EDGES, NODE_BY_ID } from "../../data/liveWorkflow";

const GROUP_DOT = {
  signal: "#28CFE0",
  iris: "#B24BD6",
  vital: "#EC61E8",
  amber: "#F2A93E",
};

export function AgentFlowSection() {
  const { t } = useLang();

  return (
    <Section
      id="agent-flow"
      eyebrow="Live Under the Hood"
      title="Watch the pipeline think, in real time."
      intro="Every reading runs through a real backend pipeline — capture, validation, three parallel organ-health scores — into the Guidance Agent, which decides for itself which of five actions to take. Nothing here is scripted: this is that pipeline's actual event stream, rendered live."
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
            .map((e) => `${t(NODE_BY_ID[e.from].labelKey)} to ${t(NODE_BY_ID[e.to].labelKey)}`)
            .join(", ")}
          . {t("liveWorkflow.srToolNote")}
        </p>
      </div>

      {/* Visible legend — doubles as the fallback's own note for sighted
          users who want the labels spelled out even with the live view up. */}
      <div
        className="mt-6 flex flex-wrap items-center justify-center gap-2 gap-y-3"
        aria-hidden="true"
      >
        {WORKFLOW_NODES.map((node) => {
          const color = GROUP_DOT[node.group];
          return (
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
          );
        })}
      </div>
    </Section>
  );
}
