import { Droplet, ScanLine, Cpu, LayoutDashboard } from "lucide-react";
import { motion } from "framer-motion";
import { Section } from "./Section";
import { staggerContainer, staggerItem } from "../ui/Reveal";

const steps = [
  {
    icon: Droplet,
    title: "Sample",
    copy: "Provide a saliva sample. No needles, under a minute.",
  },
  {
    icon: ScanLine,
    title: "Capture",
    copy: "Novera's sensor reads the biomarker signal instantly.",
  },
  {
    icon: Cpu,
    title: "Analyze",
    copy: "AI agents cross-reference it against the four screening models.",
  },
  {
    icon: LayoutDashboard,
    title: "Understand",
    copy: "View your dashboard, hear it explained, or download your report.",
  },
];

export function HowItWorksSection() {
  return (
    <Section
      id="how"
      eyebrow="The Process"
      title="From sample to summary"
    >
      <motion.ol
        className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4"
        variants={staggerContainer}
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: "0px 0px -15% 0px" }}
      >
        {steps.map((step, i) => {
          const Icon = step.icon;
          return (
            <motion.li key={step.title} variants={staggerItem} className="relative">
              <div className="glass-card h-full p-6">
                <div className="flex items-center justify-between">
                  <span className="flex h-12 w-12 items-center justify-center rounded-xl border border-white/10 bg-white/5 text-signal">
                    <Icon size={22} strokeWidth={1.75} />
                  </span>
                  <span className="font-mono text-2xl font-semibold text-white/15">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                </div>
                <h3 className="mt-5 font-display text-lg font-semibold text-white">
                  {step.title}
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-400">
                  {step.copy}
                </p>
              </div>
            </motion.li>
          );
        })}
      </motion.ol>
    </Section>
  );
}
