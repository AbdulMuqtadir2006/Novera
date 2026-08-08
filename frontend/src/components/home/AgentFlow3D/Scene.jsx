import { useEffect, useMemo, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { Line, Html } from "@react-three/drei";
import { agentFlowNodes, agentFlowEdges } from "../../../data/agentFlow";
import { helixLayout, buildArcCurve } from "./geometry";

const RADIUS = 2.35;

function NodeMarker({ node, position, reducedMotion }) {
  const glowRef = useRef();
  const coreRef = useRef();
  const seed = useMemo(() => Math.random() * Math.PI * 2, []);

  useFrame(({ clock }) => {
    if (reducedMotion) return;
    const t = clock.getElapsedTime();
    const pulse = 1 + Math.sin(t * 1.6 + seed) * 0.12;
    if (coreRef.current) coreRef.current.scale.setScalar(pulse);
    if (glowRef.current) glowRef.current.scale.setScalar(pulse * 1.8);
  });

  return (
    <group position={position}>
      <mesh ref={glowRef}>
        <sphereGeometry args={[0.16, 16, 16]} />
        <meshBasicMaterial color={node.color} transparent opacity={0.18} depthWrite={false} />
      </mesh>
      <mesh ref={coreRef}>
        <sphereGeometry args={[0.075, 20, 20]} />
        <meshBasicMaterial color={node.color} />
      </mesh>
      <Html center distanceFactor={7} style={{ pointerEvents: "none" }}>
        <div className="-translate-y-8 whitespace-nowrap">
          <span
            className="rounded-full border px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-white backdrop-blur-md"
            style={{ borderColor: `${node.color}55`, background: "rgba(8,9,25,0.6)" }}
          >
            {node.label}
          </span>
        </div>
      </Html>
    </group>
  );
}

function AgentArc({ edge, start, end, reducedMotion, bus }) {
  const curve = useMemo(() => buildArcCurve(start, end, RADIUS), [start, end]);
  const points = useMemo(() => curve.getSpacedPoints(48), [curve]);
  const pulseRef = useRef();
  const burstRef = useRef();
  const burstState = useRef({ active: false, startedAt: 0 });
  const phase = useMemo(() => Math.random(), []);
  const speed = Math.max(edge.speed ?? 0.3, 0.05);

  useEffect(() => {
    if (!bus) return;
    return bus.subscribe(({ edgeId }) => {
      if (edgeId !== edge.id) return;
      burstState.current = { active: true, startedAt: performance.now() / 1000 };
    });
  }, [bus, edge.id]);

  useFrame(({ clock }) => {
    const now = clock.getElapsedTime();

    if (!reducedMotion && pulseRef.current) {
      const t = (((now * speed + phase) % 1) + 1) % 1;
      pulseRef.current.position.copy(curve.getPointAt(t));
      const fade = Math.sin(t * Math.PI);
      pulseRef.current.material.opacity = 0.35 + fade * 0.65;
    }

    if (burstRef.current) {
      const { active, startedAt } = burstState.current;
      if (!reducedMotion && active) {
        const bt = (performance.now() / 1000 - startedAt) / 0.85;
        if (bt >= 1) {
          burstState.current.active = false;
          burstRef.current.visible = false;
        } else {
          burstRef.current.visible = true;
          burstRef.current.position.copy(curve.getPointAt(Math.min(bt, 1)));
          burstRef.current.material.opacity = 1 - bt * bt;
        }
      } else {
        burstRef.current.visible = false;
      }
    }
  });

  return (
    <group>
      <Line points={points} color={edge.color} transparent opacity={0.32} lineWidth={1.1} />
      {!reducedMotion && (
        <mesh ref={pulseRef}>
          <sphereGeometry args={[0.05, 12, 12]} />
          <meshBasicMaterial color={edge.color} transparent opacity={0.9} depthWrite={false} />
        </mesh>
      )}
      <mesh ref={burstRef} visible={false}>
        <sphereGeometry args={[0.09, 14, 14]} />
        <meshBasicMaterial color={edge.color} transparent opacity={1} depthWrite={false} />
      </mesh>
    </group>
  );
}

export function AgentFlowScene({ reducedMotion = false, bus = null }) {
  const groupRef = useRef();
  const { invalidate } = useThree();

  const positions = useMemo(() => {
    const pts = helixLayout(agentFlowNodes.length, RADIUS);
    const map = {};
    agentFlowNodes.forEach((n, i) => {
      map[n.id] = pts[i];
    });
    return map;
  }, []);

  const edges = useMemo(
    () => agentFlowEdges.filter((e) => positions[e.from] && positions[e.to]),
    [positions],
  );

  // In reduced-motion mode the group never rotates on its own, but a fired
  // event should still nudge a re-render (frameloop="demand") so the burst
  // is actually visible as at least a static flash rather than silently
  // no-op'ing.
  useEffect(() => {
    if (!reducedMotion || !bus) return;
    return bus.subscribe(() => invalidate());
  }, [reducedMotion, bus, invalidate]);

  useFrame((_, delta) => {
    if (reducedMotion || !groupRef.current) return;
    groupRef.current.rotation.y += delta * 0.08;
  });

  return (
    <group ref={groupRef} rotation={[0.15, 0, 0]}>
      <mesh>
        <sphereGeometry args={[RADIUS * 0.985, 32, 32]} />
        <meshBasicMaterial color="#28CFE0" wireframe transparent opacity={0.045} depthWrite={false} />
      </mesh>

      {edges.map((edge) => (
        <AgentArc
          key={edge.id}
          edge={edge}
          start={positions[edge.from]}
          end={positions[edge.to]}
          reducedMotion={reducedMotion}
          bus={bus}
        />
      ))}

      {agentFlowNodes.map((node) =>
        positions[node.id] ? (
          <NodeMarker
            key={node.id}
            node={node}
            position={positions[node.id]}
            reducedMotion={reducedMotion}
          />
        ) : null,
      )}
    </group>
  );
}
