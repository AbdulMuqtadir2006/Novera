import { useRef } from "react";
import { Link } from "react-router-dom";
import { motion, useMotionValue, useSpring } from "framer-motion";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";

// Primary CTA with a subtle magnetic cursor-follow (desktop only, disabled for
// reduced-motion). Renders as a router Link when `to` is set.
export function MagneticButton({ to, href, children, className = "", onClick }) {
  const ref = useRef(null);
  const reduced = usePrefersReducedMotion();
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const sx = useSpring(x, { stiffness: 200, damping: 15, mass: 0.3 });
  const sy = useSpring(y, { stiffness: 200, damping: 15, mass: 0.3 });

  const handleMove = (e) => {
    if (reduced || !ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    const relX = e.clientX - (rect.left + rect.width / 2);
    const relY = e.clientY - (rect.top + rect.height / 2);
    x.set(relX * 0.25);
    y.set(relY * 0.35);
  };
  const reset = () => {
    x.set(0);
    y.set(0);
  };

  const inner = (
    <motion.span
      ref={ref}
      style={{ x: sx, y: sy }}
      onMouseMove={handleMove}
      onMouseLeave={reset}
      className={`btn-primary ${className}`}
    >
      {children}
    </motion.span>
  );

  if (to) {
    return (
      <Link to={to} onClick={onClick} className="inline-block">
        {inner}
      </Link>
    );
  }
  if (href) {
    return (
      <a href={href} onClick={onClick} className="inline-block">
        {inner}
      </a>
    );
  }
  return (
    <button type="button" onClick={onClick} className="inline-block">
      {inner}
    </button>
  );
}
