import { Section } from "./Section";
import { AgentFlow3D } from "./AgentFlow3D";
import { agentFlowNodes, agentFlowEdges } from "../../data/agentFlow";

export function AgentFlowSection() {
  return (
    <Section
      id="agent-flow"
      eyebrow="Live Under the Hood"
      title="Watch control pass from agent to agent."
      intro="Every reading runs a real handoff chain — capture, analysis, insight — into Guidance, the manager that dispatches your spoken summary, your report, and, only if a clinical threshold is crossed, a WhatsApp escalation. This is that pipeline, rendered."
    >
      <div className="glass-card relative h-[440px] overflow-hidden sm:h-[520px] md:h-[600px]">
        <div
          className="pointer-events-none absolute inset-0 grid-lines opacity-30"
          aria-hidden="true"
        />
        <AgentFlow3D />

        {/* Accessible text alternative — canvas pixels aren't readable by
            assistive tech, so the same pipeline is spelled out here. */}
        <p className="sr-only">
          Agent pipeline, in order: {agentFlowNodes.map((n) => n.label).join(" → ")}. Connections:{" "}
          {agentFlowEdges
            .map((e) => {
              const from = agentFlowNodes.find((n) => n.id === e.from)?.label ?? e.from;
              const to = agentFlowNodes.find((n) => n.id === e.to)?.label ?? e.to;
              return `${from} to ${to}`;
            })
            .join(", ")}
          .
        </p>
      </div>

      {/* Visible legend — doubles as the fallback's own note for sighted
          users who want the labels spelled out even with the 3D view up. */}
      <div
        className="mt-6 flex flex-wrap items-center justify-center gap-2 gap-y-3"
        aria-hidden="true"
      >
        {agentFlowNodes.map((node) => (
          <span
            key={node.id}
            className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 font-mono text-xs text-slate-300"
          >
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{ backgroundColor: node.color, boxShadow: `0 0 8px ${node.color}` }}
            />
            {node.label}
          </span>
        ))}
      </div>
    </Section>
  );
}
