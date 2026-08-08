import * as THREE from "three";

// Deterministic small hash -> [-1, 1], used for a stable per-node z-jitter
// (so re-renders don't reshuffle depth, but we don't need to hardcode it
// per node either).
function hashUnit(id) {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return (h % 1000) / 500 - 1; // -> [-1, 1)
}

// Lays out an arbitrary directed graph (nodes + {from,to} edges) as a
// left-to-right flowchart: each node's column ("depth") is one more than
// the deepest parent that points to it, roots start at depth 0. Nodes
// sharing a depth are stacked vertically, centered. This is what makes a
// "manager" node that fans out to several children read as a visible fan,
// and it's fully data-driven — add/remove nodes or edges and the layout
// just adapts, no hardcoded positions or node count.
export function layeredFlowLayout(nodes, edges, { xSpacing = 2.3, ySpacing = 1.35, zJitter = 0.55 } = {}) {
  const depth = new Map(nodes.map((n) => [n.id, 0]));
  const ids = new Set(nodes.map((n) => n.id));
  const validEdges = edges.filter((e) => ids.has(e.from) && ids.has(e.to));

  // Relaxation pass (nodes.length iterations is enough to settle any DAG
  // this small; a cycle just stops improving, which is an acceptable
  // degradation rather than an infinite loop).
  for (let pass = 0; pass < nodes.length; pass++) {
    let changed = false;
    for (const e of validEdges) {
      const next = depth.get(e.from) + 1;
      if (next > depth.get(e.to)) {
        depth.set(e.to, next);
        changed = true;
      }
    }
    if (!changed) break;
  }

  const layers = new Map();
  for (const n of nodes) {
    const d = depth.get(n.id);
    if (!layers.has(d)) layers.set(d, []);
    layers.get(d).push(n.id);
  }

  const maxDepth = Math.max(0, ...Array.from(layers.keys()));
  const positions = {};
  for (const [d, idsInLayer] of layers) {
    const count = idsInLayer.length;
    idsInLayer.forEach((id, i) => {
      const x = (d - maxDepth / 2) * xSpacing;
      const y = (i - (count - 1) / 2) * ySpacing;
      const z = hashUnit(id) * zJitter;
      positions[id] = new THREE.Vector3(x, y, z);
    });
  }
  return positions;
}

// A gentle 3D bow between two nodes — bows upward and slightly toward the
// camera so edges read as cables floating in space rather than flat lines,
// without assuming any spherical/globe layout.
export function buildArcCurve(start, end, { lift = 0.55 } = {}) {
  const mid = start.clone().add(end).multiplyScalar(0.5);
  const dist = start.distanceTo(end);
  const bow = lift + dist * 0.16;
  const control = mid.clone().add(new THREE.Vector3(0, bow, bow * 0.5));
  return new THREE.QuadraticBezierCurve3(start.clone(), control, end.clone());
}
