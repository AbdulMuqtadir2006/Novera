import { Canvas } from "@react-three/fiber";
import { AgentFlowScene } from "./Scene";

// Isolated in its own module (rather than living in AgentFlow3D.jsx) so the
// lazy() import boundary keeps three.js/@react-three/* out of the main
// bundle entirely until this section actually scrolls into view.
export default function Canvas3D({ active, reducedMotion, bus }) {
  return (
    <Canvas
      dpr={[1, 2]}
      camera={{ position: [0, 1.4, 8], fov: 44 }}
      gl={{ antialias: true, alpha: true, powerPreference: "low-power" }}
      frameloop={!active ? "never" : reducedMotion ? "demand" : "always"}
    >
      <AgentFlowScene reducedMotion={reducedMotion} bus={bus} />
    </Canvas>
  );
}
