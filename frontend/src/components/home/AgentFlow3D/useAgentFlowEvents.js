// Minimal pub/sub so a parent component can fire one-off pulses on a given
// edge (e.g. "guidance-voice") without threading refs through the whole R3F
// tree. One bus instance per <AgentFlow3D>, created fresh per mount and
// handed down through props — not a module-level singleton, so multiple
// instances of the visualization on a page never cross-talk.
export function createAgentFlowBus() {
  const target = new EventTarget();
  return {
    fire(edgeId, detail = {}) {
      target.dispatchEvent(new CustomEvent("pulse", { detail: { edgeId, ...detail } }));
    },
    subscribe(handler) {
      const listener = (e) => handler(e.detail);
      target.addEventListener("pulse", listener);
      return () => target.removeEventListener("pulse", listener);
    },
  };
}
