import { useRef } from "react";
import { motion, useMotionValue, useSpring, useTransform } from "framer-motion";
import { Section } from "./Section";
import { healthAreas } from "../../data/healthAreas";
import { staggerContainer, staggerItem } from "../ui/Reveal";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";

function TiltCard({ area }) {
  const Icon = area.icon;
  const ref = useRef(null);
  const reduced = usePrefersReducedMotion();
  const mx = useMotionValue(0.5);
  const my = useMotionValue(0.5);
  const rotateX = useSpring(useTransform(my, [0, 1], [6, -6]), {
    stiffness: 200,
    damping: 20,
  });
  const rotateY = useSpring(useTransform(mx, [0, 1], [-6, 6]), {
    stiffness: 200,
    damping: 20,
  });

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
    <motion.div variants={staggerItem} style={{ perspective: 900 }}>
      <motion.div
        ref={ref}
        onMouseMove={onMove}
        onMouseLeave={onLeave}
        style={reduced ? undefined : { rotateX, rotateY, transformStyle: "preserve-3d" }}
        className="group glass-card relative h-full overflow-hidden p-7 transition-colors duration-300 hover:border-signal/40"
      >
        <span className="relative flex h-14 w-14 items-center justify-center rounded-2xl border border-signal/20 bg-signal/5 text-signal transition-colors duration-300 group-hover:bg-signal/10">
          <Icon size={26} strokeWidth={1.75} />
        </span>
        <h3 className="mt-6 font-display text-xl font-semibold text-white">
          {area.name}
        </h3>
        <p className="mt-3 text-sm leading-relaxed text-slate-400">{area.copy}</p>
        <div className="pointer-events-none absolute -right-10 -top-10 h-28 w-28 rounded-full bg-signal/0 blur-3xl transition-colors duration-500 group-hover:bg-signal/25" />
      </motion.div>
    </motion.div>
  );
}

export function HealthAreasSection() {
  return (
    <Section
      id="health-areas"
      eyebrow="What It Screens"
      title="Health Areas"
      intro="Our research platform currently explores screening signals in four health areas."
    >
      <motion.div
        className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4"
        variants={staggerContainer}
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: "0px 0px -15% 0px" }}
      >
        {healthAreas.map((area) => (
          <TiltCard key={area.id} area={area} />
        ))}
      </motion.div>
    </Section>
  );
}
