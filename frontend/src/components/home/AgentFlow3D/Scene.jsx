import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { useFrame, useThree } from "@react-three/fiber";
import { Line, Html, Grid } from "@react-three/drei";
import { agentFlowNodes, agentFlowEdges } from "../../../data/agentFlow";
import { layeredFlowLayout, buildArcCurve } from "./geometry";

function NodeMarker({ node, position, reducedMotion }) {
  const glowRef = useRef();
  const coreRef = useRef();
  const ringRef = useRef();
  const isManager = node.role === "manager";
  const coreSize = isManager ? 0.115 : 0.075;
  const seed = useMemo(() => Math.random() * Math.PI * 2, []);

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    if (!reducedMotion) {
      const pulse = 1 + Math.sin(t * 1.6 + seed) * 0.12;
      if (coreRef.current) coreRef.current.scale.setScalar(pulse);
      if (glowRef.current) glowRef.current.scale.setScalar(pulse * 1.8);
    }
    if (ringRef.current && !reducedMotion) {
      ringRef.current.rotation.z = t * 0.6;
    }
  });

  return (
    <group position={position}>
      {isManager && (
        <mesh ref={ringRef} rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[coreSize * 2.4, 0.012, 8, 48]} />
          <meshBasicMaterial color={node.color} transparent opacity={0.55} depthWrite={false} />
        </mesh>
      )}
      <mesh ref={glowRef}>
        <sphereGeometry args={[coreSize * 2.1, 16, 16]} />
        <meshBasicMaterial color={node.color} transparent opacity={isManager ? 0.22 : 0.18} depthWrite={false} />
      </mesh>
      <mesh ref={coreRef}>
        <sphereGeometry args={[coreSize, 20, 20]} />
        <meshBasicMaterial color={node.color} />
      </mesh>
      <Html center distanceFactor={7} style={{ pointerEvents: "none" }}>
        <div className="-translate-y-9 flex flex-col items-center whitespace-nowrap">
          <span
            className={`rounded-full border px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-white backdrop-blur-md ${isManager ? "font-bold" : ""}`}
            style={{
              borderColor: `${node.color}${isManager ? "aa" : "55"}`,
              background: isManager ? "rgba(178,75,214,0.18)" : "rgba(8,9,25,0.6)",
            }}
          >
            {node.label}
            {isManager && <span className="ml-1.5 opacity-70">· Manager</span>}
          </span>
        </div>
      </Html>
    </group>
  );
}

function AgentArc({ edge, start, end, reducedMotion, bus }) {
  const curve = useMemo(() => buildArcCurve(start, end), [start, end]);
  const points = useMemo(() => curve.getSpacedPoints(48), [curve]);
  const pulseRef = useRef();
  const burstRef = useRef();
  const burstState = useRef({ active: false, startedAt: 0 });
  const phase = useMemo(() => Math.random(), []);
  const speed = Math.max(edge.speed ?? 0.3, 0.05);
  const isActive = edge.status !== "idle";

  useEffect(() => {
    if (!bus) return;
    return bus.subscribe(({ edgeId }) => {
      if (edgeId !== edge.id) return;
      burstState.current = { active: true, startedAt: performance.now() / 1000 };
    });
  }, [bus, edge.id]);

  useFrame(({ clock }) => {
    const now = clock.getElapsedTime();

    if (!reducedMotion && isActive && pulseRef.current) {
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
      <Line
        points={points}
        color={edge.color}
        transparent
        opacity={isActive ? 0.32 : 0.14}
        lineWidth={1.1}
        dashed={!isActive}
        dashScale={6}
      />
      {!reducedMotion && isActive && (
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

  const positions = useMemo(
    () => layeredFlowLayout(agentFlowNodes, agentFlowEdges),
    [],
  );

  const edges = useMemo(
    () => agentFlowEdges.filter((e) => positions[e.from] && positions[e.to]),
    [positions],
  );

  const bounds = useMemo(() => {
    const values = Object.values(positions);
    const xs = values.map((v) => v.x);
    const ys = values.map((v) => v.y);
    return {
      minX: Math.min(...xs),
      maxX: Math.max(...xs),
      minY: Math.min(...ys),
      maxY: Math.max(...ys),
    };
  }, [positions]);

  // Fits the camera to the actual content bounds + current viewport aspect,
  // instead of a guessed fixed distance — the flowchart's width scales with
  // however many output agents fan out, and the container's aspect ratio
  // swings from wide (desktop) to near-square (mobile), so a fixed camera
  // would crop one or the other.
  const { camera, size } = useThree();
  useEffect(() => {
    const marginX = 1.4;
    const marginY = 1.7;
    const halfWidth = ((bounds.maxX - bounds.minX) / 2) * marginX + 0.6;
    const halfHeight = ((bounds.maxY - bounds.minY) / 2) * marginY + 0.6;
    const aspect = size.width / Math.max(size.height, 1);
    const vFov = THREE.MathUtils.degToRad(camera.fov);
    const distForHeight = halfHeight / Math.tan(vFov / 2);
    const distForWidth = halfWidth / (Math.tan(vFov / 2) * Math.max(aspect, 0.5));
    const distance = Math.max(distForHeight, distForWidth, 4);
    camera.position.set(0, Math.min(1.4, halfHeight * 0.4), distance);
    camera.lookAt(0, 0, 0);
    camera.updateProjectionMatrix();
  }, [bounds, size.width, size.height, camera]);

  // In reduced-motion mode the group never sways on its own, but a fired
  // event should still nudge a re-render (frameloop="demand") so the burst
  // is actually visible as at least a static flash rather than silently
  // no-op'ing.
  useEffect(() => {
    if (!reducedMotion || !bus) return;
    return bus.subscribe(() => invalidate());
  }, [reducedMotion, bus, invalidate]);

  // Gentle side-to-side sway rather than a full spin — this is a flowchart
  // with a legible left-to-right direction, not a globe, so it should never
  // rotate far enough to read backwards or upside down.
  useFrame(({ clock }) => {
    if (reducedMotion || !groupRef.current) return;
    groupRef.current.rotation.y = Math.sin(clock.getElapsedTime() * 0.15) * 0.14;
  });

  return (
    <>
      <Grid
        position={[0, bounds.minY - 1.1, 0]}
        args={[bounds.maxX - bounds.minX + 6, 6]}
        cellSize={0.5}
        cellThickness={0.5}
        cellColor="#28CFE0"
        sectionSize={2.5}
        sectionThickness={0.8}
        sectionColor="#B24BD6"
        fadeDistance={12}
        fadeStrength={1.5}
        infiniteGrid={false}
      />
      <group ref={groupRef} rotation={[0.05, 0, 0]}>
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
    </>
  );
}
