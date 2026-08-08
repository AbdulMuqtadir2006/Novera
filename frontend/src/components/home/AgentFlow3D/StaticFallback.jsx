import { agentFlowNodes } from "../../../data/agentFlow";

// Rendered when WebGL isn't available at all (old/software-rendering
// browsers, GPU-blocklisted devices) so the section still communicates the
// pipeline instead of going blank.
export function StaticFallback() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-6 px-4">
      <div className="flex flex-wrap items-center justify-center gap-x-2 gap-y-4">
        {agentFlowNodes.map((node, i) => (
          <div key={node.id} className="flex items-center gap-2">
            <span
              className="rounded-full border px-3 py-1.5 font-mono text-xs uppercase tracking-wider text-white"
              style={{ borderColor: `${node.color}55`, background: "rgba(255,255,255,0.04)" }}
            >
              {node.label}
            </span>
            {i < agentFlowNodes.length - 1 && (
              <span className="h-px w-6 bg-gradient-to-r from-signal/40 to-vital/40" aria-hidden="true" />
            )}
          </div>
        ))}
      </div>
      <p className="max-w-sm text-center text-xs text-slate-500">
        Your browser can't render the interactive 3D view — showing the pipeline order instead.
      </p>
    </div>
  );
}
