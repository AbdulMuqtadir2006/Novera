import * as THREE from "three";

// Places `count` nodes along a gentle helix wrapped around an imaginary
// sphere of the given radius, ordered top-to-bottom in data order. This
// reads as a directional "flow" (works for any node count, not hardcoded)
// rather than a random scatter, while still living in the abstract 3D
// orbit space the brief called for.
export function helixLayout(count, radius, { turns = 1.4, poleGap = 0.22 } = {}) {
  if (count <= 0) return [];
  const positions = [];
  for (let i = 0; i < count; i++) {
    const t = count === 1 ? 0.5 : i / (count - 1);
    // keep nodes off the exact poles so they don't visually bunch up
    const phi = THREE.MathUtils.lerp(poleGap, Math.PI - poleGap, t);
    const theta = t * turns * Math.PI * 2;
    const x = radius * Math.sin(phi) * Math.cos(theta);
    const y = radius * Math.cos(phi);
    const z = radius * Math.sin(phi) * Math.sin(theta);
    positions.push(new THREE.Vector3(x, y, z));
  }
  return positions;
}

// A great-circle-ish arc between two points, bulging outward from the
// sphere's center — the same visual language as flight-path/network-traffic
// globes, just applied to an abstract agent-pipeline space instead of
// geography. Longer hops arc higher than short ones.
export function buildArcCurve(start, end, radius) {
  const mid = start.clone().add(end).multiplyScalar(0.5);
  const dist = start.distanceTo(end);
  const outward = mid.lengthSq() > 1e-6 ? mid.clone().normalize() : new THREE.Vector3(0, 1, 0);
  const lift = radius * 0.32 + dist * 0.3;
  const control = mid.add(outward.multiplyScalar(lift));
  return new THREE.QuadraticBezierCurve3(start.clone(), control, end.clone());
}
