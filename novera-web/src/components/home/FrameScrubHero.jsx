import { useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown } from "lucide-react";
import { useScrollFrameSequence } from "../../hooks/useScrollFrameSequence";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";
import { FloatingOrbs } from "./FloatingOrbs";

// The left-hand headline + paragraph change as the product forms on scroll.
const STAGES = [
  {
    eyebrow: "Novera Research Platform",
    line1: "One sample.",
    line2: "A full picture.",
    para: "Saliva carries more signal than we give it credit for. Novera's sensors capture it, and a system of AI agents cleans, cross-references, and explains it.",
  },
  {
    eyebrow: "01 · Capture",
    line1: "Capturing",
    line2: "the signal.",
    para: "The moment your sample meets the sensor, Novera reads the raw biomarker signal — pH, creatinine, urea, and temperature.",
  },
  {
    eyebrow: "02 · Analyse",
    line1: "Cross-referencing",
    line2: "biomarkers.",
    para: "A coordinated system of AI agents checks the reading against research models for kidney, hydration, oral and digestive health.",
  },
  {
    eyebrow: "03 · Model",
    line1: "Modeling",
    line2: "your screening.",
    para: "Every value is scored against its reference range and your own history — building a picture that is actually yours.",
  },
  {
    eyebrow: "04 · Result",
    line1: "Your result,",
    line2: "assembled.",
    para: "A short sample becomes a screening summary you can read in minutes — clear, calm, and honest.",
  },
];

const EASE = [0.16, 1, 0.3, 1];

export function FrameScrubHero() {
  const canvasRef = useRef(null);
  const sectionRef = useRef(null);
  const reduced = usePrefersReducedMotion();
  const { ready, progress, loadProgress } = useScrollFrameSequence(canvasRef, sectionRef, !reduced);

  const stage = Math.min(STAGES.length - 1, Math.floor(progress * STAGES.length));
  const s = STAGES[stage];
  const scrollCueVisible = progress < 0.05 && !reduced;

  return (
    <section
      ref={sectionRef}
      className="relative h-dvh w-full overflow-hidden bg-ink"
      aria-label="Novera product reveal"
    >
      {/* Frame canvas */}
      <canvas ref={canvasRef} className="absolute inset-0 z-0 h-full w-full" aria-hidden="true" />

      {/* Legibility scrim — dark on the left so the copy always reads, plus a
          soft top/bottom fade. Leaves the centre/right where the product forms. */}
      <div
        className="pointer-events-none absolute inset-0 z-0"
        style={{
          background:
            "linear-gradient(to right, rgba(8,9,25,0.92) 0%, rgba(8,9,25,0.6) 30%, rgba(8,9,25,0.12) 55%, transparent 72%), linear-gradient(to bottom, rgba(8,9,25,0.6) 0%, transparent 20%, transparent 68%, rgba(8,9,25,0.85) 100%)",
        }}
        aria-hidden="true"
      />

      {/* Many white glowing orbs, floating over the scene */}
      <FloatingOrbs />

      {/* Preload state */}
      <AnimatePresence>
        {!ready && (
          <motion.div
            className="absolute inset-0 z-30 flex flex-col items-center justify-center bg-ink"
            initial={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.5 }}
          >
            <div className="flex flex-col items-center gap-5">
              <span className="relative flex h-3 w-3">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-signal/60" />
                <span className="relative inline-flex h-3 w-3 rounded-full bg-signal" />
              </span>
              <div className="h-[3px] w-52 overflow-hidden rounded-full bg-white/10">
                <div
                  className="h-full rounded-full bg-signal transition-[width] duration-200 ease-out"
                  style={{ width: `${Math.round(loadProgress * 100)}%` }}
                />
              </div>
              <span className="font-mono text-[11px] uppercase tracking-[0.28em] text-slate-400">
                Priming sensor · {Math.round(loadProgress * 100)}%
              </span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Left-hand headline block — changes through scroll stages, on top of the frames */}
      <div className="pointer-events-none absolute inset-y-0 left-0 z-20 flex w-full max-w-xl flex-col justify-center px-6 text-left sm:px-10 md:max-w-2xl md:pl-16">
        <AnimatePresence mode="wait">
          <motion.div
            key={stage}
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -18 }}
            transition={{ duration: 0.5, ease: EASE }}
          >
            <p className="mb-4 font-mono text-xs font-medium uppercase tracking-[0.28em] text-white/70">
              {s.eyebrow}
            </p>
            <h1 className="text-balance font-display text-5xl font-extrabold leading-[1.03] text-white sm:text-7xl md:text-8xl">
              {s.line1}
              <br />
              <span className="text-white">{s.line2}</span>
            </h1>
            <p className="mt-6 max-w-lg text-pretty text-lg leading-relaxed text-slate-200/85 sm:text-xl">
              {s.para}
            </p>
          </motion.div>
        </AnimatePresence>

        {/* stage progress dots */}
        <div className="mt-8 flex gap-2">
          {STAGES.map((_, i) => (
            <span
              key={i}
              className={`h-1.5 rounded-full transition-all duration-300 ${
                i === stage ? "w-7 bg-signal" : "w-1.5 bg-white/25"
              }`}
            />
          ))}
        </div>
      </div>

      {/* Scroll cue */}
      <AnimatePresence>
        {scrollCueVisible && ready && (
          <motion.div
            className="absolute inset-x-0 bottom-6 z-20 flex flex-col items-center gap-1"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.4 }}
          >
            <span className="font-mono text-[11px] uppercase tracking-[0.2em] text-slate-400">
              Scroll to watch it come together
            </span>
            <motion.span
              animate={{ y: [0, 6, 0] }}
              transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
            >
              <ChevronDown size={18} className="text-signal" />
            </motion.span>
          </motion.div>
        )}
      </AnimatePresence>

      {reduced && ready && (
        <div className="absolute inset-x-0 bottom-6 z-20 text-center">
          <span className="font-mono text-[11px] uppercase tracking-[0.2em] text-slate-500">
            Motion reduced · showing assembled result
          </span>
        </div>
      )}
    </section>
  );
}
