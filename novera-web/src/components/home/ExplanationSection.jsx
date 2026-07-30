import { Section } from "./Section";
import { Reveal } from "../ui/Reveal";

export function ExplanationSection() {
  return (
    <Section
      id="what"
      eyebrow="The Idea"
      title="Health screening shouldn't need a needle."
    >
      <div className="grid gap-10 md:grid-cols-[1.6fr_1fr] md:items-start">
        <Reveal delay={0.05}>
          <p className="text-pretty text-lg leading-relaxed text-slate-300">
            Traditional screening means blood draws, lab queues, and days of
            waiting. Novera reads biomarker signals directly from saliva instead.
            A sample goes into the sensor; a system of AI agents takes it from
            there — checking the signal against research models for kidney
            function, hydration, oral health, and digestive health, and returning
            a screening summary in minutes.
          </p>
        </Reveal>

        <Reveal delay={0.15}>
          <div className="glass-card p-6">
            <p className="text-sm leading-relaxed text-slate-400">
              This is a research platform, not a diagnostic device — built to
              explore what saliva can tell us, faster than conventional screening
              allows.
            </p>
            <div className="mt-6 flex items-center gap-3 border-t border-white/10 pt-5">
              <span className="relative flex h-2.5 w-2.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-signal/50" />
                <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-signal" />
              </span>
              <span className="font-mono text-xs uppercase tracking-[0.2em] text-signal">
                Research-stage platform
              </span>
            </div>
          </div>
        </Reveal>
      </div>
    </Section>
  );
}
