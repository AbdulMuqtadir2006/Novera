import {
  Suspense,
  forwardRef,
  lazy,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import { usePrefersReducedMotion } from "../../../hooks/usePrefersReducedMotion";
import { createAgentFlowBus } from "./useAgentFlowEvents";
import { FlowErrorBoundary } from "./FlowErrorBoundary";
import { StaticFallback } from "./StaticFallback";

const Canvas3D = lazy(() => import("./Canvas3D"));

// Stable reference (not re-created per render) so the IntersectionObserver
// effect below doesn't tear down/recreate its observer on every render.
const IO_OPTIONS = { rootMargin: "200px 0px", threshold: 0.01 };

/**
 * 3D visualization of the agent pipeline: nodes = agents/steps
 * (src/data/agentFlow.js), animated arcs = control/data handoffs, a
 * traveling pulse per arc reads as "data is flowing right now."
 *
 * Fully data-driven — edit src/data/agentFlow.js to add/remove
 * agents/connections, no component changes needed.
 *
 * Imperative API (via ref): fireEvent(edgeId) fires a one-off bright pulse
 * along a specific connection, e.g. when a real handoff happens:
 *   const flowRef = useRef(null);
 *   <AgentFlow3D ref={flowRef} />
 *   flowRef.current?.fireEvent("guidance-voice");
 */
export const AgentFlow3D = forwardRef(function AgentFlow3D(_props, ref) {
  const containerRef = useRef(null);
  const [inView, setInView] = useState(false);
  const [hasLoaded, setHasLoaded] = useState(false);
  const reducedMotion = usePrefersReducedMotion();
  const bus = useMemo(() => createAgentFlowBus(), []);

  useImperativeHandle(ref, () => ({
    fireEvent: (edgeId, detail) => bus.fire(edgeId, detail),
  }));

  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof IntersectionObserver === "undefined") {
      setInView(true);
      return;
    }
    const observer = new IntersectionObserver(([entry]) => {
      setInView(entry.isIntersecting);
    }, IO_OPTIONS);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (inView) setHasLoaded(true);
  }, [inView]);

  return (
    <div ref={containerRef} className="relative h-full w-full">
      <FlowErrorBoundary fallback={<StaticFallback />}>
        {hasLoaded ? (
          <Suspense fallback={<div className="h-full w-full" aria-hidden="true" />}>
            <Canvas3D active={inView} reducedMotion={reducedMotion} bus={bus} />
          </Suspense>
        ) : (
          <div className="h-full w-full" aria-hidden="true" />
        )}
      </FlowErrorBoundary>
    </div>
  );
});
