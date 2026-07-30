import { motion } from "framer-motion";

// Scroll-triggered reveal. Fades/slides its children up when they enter the
// viewport. Framer Motion honours prefers-reduced-motion via `useReducedMotion`
// internally when we pass a distance of 0, but we also gate the offset here.
const EASE = [0.16, 1, 0.3, 1];

export function Reveal({
  children,
  delay = 0,
  y = 24,
  className = "",
  once = true,
  as = "div",
}) {
  const MotionTag = motion[as] || motion.div;
  return (
    <MotionTag
      className={className}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once, margin: "0px 0px -12% 0px" }}
      transition={{ duration: 0.6, ease: EASE, delay }}
    >
      {children}
    </MotionTag>
  );
}

// Stagger container + item for grids/lists.
export const staggerContainer = {
  hidden: {},
  show: {
    transition: { staggerChildren: 0.09, delayChildren: 0.05 },
  },
};

export const staggerItem = {
  hidden: { opacity: 0, y: 28 },
  show: { opacity: 1, y: 0, transition: { duration: 0.6, ease: EASE } },
};
