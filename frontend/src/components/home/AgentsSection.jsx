import { motion } from "framer-motion";
import { Section } from "./Section";
import { agents } from "../../data/agents";
import { staggerContainer, staggerItem } from "../ui/Reveal";

function AgentCard({ agent, index }) {
  const Icon = agent.icon;
  return (
    <motion.div
      variants={staggerItem}
      className="group relative"
      whileHover={{ y: -6 }}
      transition={{ type: "spring", stiffness: 300, damping: 22 }}
    >
      <div className="glass-card relative h-full overflow-hidden p-6 transition-colors duration-300 group-hover:border-signal/40">
        {/* step index */}
        <span className="font-mono text-xs text-slate-500">
          0{index + 1}
        </span>

        {/* pulsing icon */}
        <div className="relative mt-4 inline-flex h-14 w-14 items-center justify-center">
          <span className="absolute inset-0 rounded-2xl bg-signal/10" />
          <span className="absolute inset-0 animate-pulse-ring rounded-2xl border border-signal/40" />
          <span className="relative flex h-14 w-14 items-center justify-center rounded-2xl border border-signal/30 bg-ink/60 text-signal">
            <Icon size={24} strokeWidth={1.75} />
          </span>
        </div>

        <h3 className="mt-6 font-display text-lg font-semibold text-white">
          {agent.name}
        </h3>
        <p className="mt-2 text-sm leading-relaxed text-slate-400">{agent.copy}</p>

        {/* hover glow wash */}
        <div className="pointer-events-none absolute -bottom-16 left-1/2 h-32 w-32 -translate-x-1/2 rounded-full bg-signal/0 blur-2xl transition-colors duration-500 group-hover:bg-signal/20" />
      </div>
    </motion.div>
  );
}

export function AgentsSection() {
  return (
    <Section
      id="agents"
      eyebrow="How It Thinks"
      title="A pipeline of agents, working while you wait."
      intro="Every reading passes through a coordinated system of AI agents, each responsible for a different part of turning a raw signal into something you can understand."
    >
      <div className="relative">
        {/* Animated connecting line behind the cards (desktop) */}
        <svg
          className="pointer-events-none absolute left-0 right-0 top-[132px] hidden h-2 w-full md:block"
          viewBox="0 0 1000 4"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <line
            x1="60"
            y1="2"
            x2="940"
            y2="2"
            stroke="rgba(40,207,224,0.15)"
            strokeWidth="2"
          />
          <motion.line
            x1="60"
            y1="2"
            x2="940"
            y2="2"
            stroke="#28CFE0"
            strokeWidth="2"
            strokeLinecap="round"
            initial={{ pathLength: 0 }}
            whileInView={{ pathLength: 1 }}
            viewport={{ once: true, margin: "0px 0px -20% 0px" }}
            transition={{ duration: 1.6, ease: [0.16, 1, 0.3, 1], delay: 0.3 }}
          />
        </svg>

        <motion.div
          className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4"
          variants={staggerContainer}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: "0px 0px -15% 0px" }}
        >
          {agents.map((agent, i) => (
            <AgentCard key={agent.id} agent={agent} index={i} />
          ))}
        </motion.div>
      </div>
    </Section>
  );
}
