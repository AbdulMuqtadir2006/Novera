import { useRef } from "react";
import { motion, useMotionValue, useSpring, useTransform } from "framer-motion";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";

// Cursor-driven 3D tilt card — same mouse-parallax technique as the
// homepage's health-area cards (components/home/HealthAreasSection.jsx),
// reused here on the light "paper" card surface the rest of the app's nav
// pages use, instead of that page's dark glass-card.
export function Tilt3DCard({ children, className = "", highlight = false }) {
  const ref = useRef(null);
  const reduced = usePrefersReducedMotion();
  const mx = useMotionValue(0.5);
  const my = useMotionValue(0.5);
  const rotateX = useSpring(useTransform(my, [0, 1], [7, -7]), { stiffness: 220, damping: 20 });
  const rotateY = useSpring(useTransform(mx, [0, 1], [-7, 7]), { stiffness: 220, damping: 20 });
  const glowX = useTransform(mx, [0, 1], ["0%", "100%"]);
  const glowY = useTransform(my, [0, 1], ["0%", "100%"]);

  const onMove = (e) => {
    if (reduced || !ref.current) return;
    const r = ref.current.getBoundingClientRect();
    mx.set((e.clientX - r.left) / r.width);
    my.set((e.clientY - r.top) / r.height);
  };
  const onLeave = () => {
    mx.set(0.5);
    my.set(0.5);
  };

  return (
    <div style={{ perspective: 1000 }} className={className}>
      <motion.div
        ref={ref}
        onMouseMove={onMove}
        onMouseLeave={onLeave}
        style={reduced ? undefined : { rotateX, rotateY, transformStyle: "preserve-3d" }}
        className={`light-card group relative flex h-full flex-col overflow-hidden p-6 transition-shadow duration-300 ${
          highlight ? "border-vital/40 shadow-lift" : "hover:shadow-lift"
        }`}
      >
        {!reduced && (
          <motion.div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
            style={{
              background: `radial-gradient(300px circle at ${glowX} ${glowY}, rgba(40,207,224,0.14), transparent 65%)`,
            }}
          />
        )}
        <div style={{ transform: reduced ? undefined : "translateZ(24px)" }} className="relative flex h-full flex-col">
          {children}
        </div>
      </motion.div>
    </div>
  );
}
