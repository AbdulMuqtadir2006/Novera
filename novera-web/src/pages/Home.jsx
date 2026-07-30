import { motion } from "framer-motion";
import { FrameScrubHero } from "../components/home/FrameScrubHero";
import { ExplanationSection } from "../components/home/ExplanationSection";
import { AgentsSection } from "../components/home/AgentsSection";
import { HealthAreasSection } from "../components/home/HealthAreasSection";
import { HowItWorksSection } from "../components/home/HowItWorksSection";
import { CtaSection } from "../components/home/CtaSection";

export default function Home() {
  return (
    <motion.main
      className="relative bg-ink"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.3 }}
    >
      <FrameScrubHero />

      {/* Ambient backdrop for the content sections below the hero */}
      <div className="relative">
        <div className="pointer-events-none absolute inset-0 grid-lines opacity-40" aria-hidden="true" />
        <div
          className="pointer-events-none absolute -left-40 top-40 h-[400px] w-[400px] animate-drift-a rounded-full bg-signal/[0.07] blur-[120px]"
          aria-hidden="true"
        />
        <div
          className="pointer-events-none absolute -right-40 top-[1400px] h-[420px] w-[420px] animate-drift-b rounded-full bg-vital/[0.06] blur-[120px]"
          aria-hidden="true"
        />

        <div className="relative">
          <ExplanationSection />
          <AgentsSection />
          <HealthAreasSection />
          <HowItWorksSection />
          <CtaSection />
        </div>
      </div>
    </motion.main>
  );
}
