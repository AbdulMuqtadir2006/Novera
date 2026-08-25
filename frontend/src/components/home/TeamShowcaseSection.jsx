import { motion } from "framer-motion";
import { FileText, TestTube2, Trophy } from "lucide-react";
import { Section } from "./Section";
import { ImageSlideshow } from "./ImageSlideshow";
import { staggerContainer, staggerItem } from "../ui/Reveal";
import { RESEARCH_PAPER, TEAM_PHOTOS, TESTING_PHOTOS } from "../../data/showcase";

function PanelLabel({ icon: Icon, children }) {
  return (
    <p className="mb-3 flex items-center gap-2 text-sm font-semibold text-white">
      <Icon size={16} className="text-signal" /> {children}
    </p>
  );
}

function PanelCaption({ children }) {
  return <p className="mt-3 text-sm leading-relaxed text-slate-400">{children}</p>;
}

// Single static image (not a slideshow) — optionally links out if a URL for
// the published paper is set in data/showcase.js.
function PaperPanel() {
  if (!RESEARCH_PAPER.image) {
    return (
      <div className="flex aspect-[4/3] w-full flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-white/15 bg-white/[0.02] text-slate-500">
        <FileText size={28} strokeWidth={1.5} />
        <span className="text-xs font-medium">Paper coming soon</span>
      </div>
    );
  }
  // object-contain, not object-cover (2026-08-25) — the actual paper photo
  // is a tall document page (ratio ~0.7), and cropping it to fill a 4:3 box
  // would cut off real content. bg-ink/40 fills the letterbox space.
  const img = (
    <img
      src={RESEARCH_PAPER.image}
      alt="Novera research paper"
      className="aspect-[4/3] w-full rounded-2xl border border-white/10 bg-ink/40 object-contain"
    />
  );
  return RESEARCH_PAPER.link ? (
    <a href={RESEARCH_PAPER.link} target="_blank" rel="noreferrer" className="block transition-opacity hover:opacity-90">
      {img}
    </a>
  ) : (
    img
  );
}

// "Behind Novera" (2026-08-24) — sits between AgentsSection ("How It
// Thinks") and AgentFlowSection (the live workflow diagram) on the
// homepage. Three panels: the team, the research paper, and product
// testing — a human counterweight right before the diagram that shows the
// agent's own reasoning.
export function TeamShowcaseSection() {
  return (
    <Section
      id="behind-novera"
      eyebrow="Behind Novera"
      title="The team, the research, the testing."
      intro="A glimpse at the people and the work behind the agent below — real team, real research, real hands-on testing."
    >
      <motion.div
        className="grid gap-6 sm:grid-cols-3"
        variants={staggerContainer}
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: "0px 0px -15% 0px" }}
      >
        <motion.div variants={staggerItem}>
          <PanelLabel icon={Trophy}>Our Team</PanelLabel>
          <ImageSlideshow images={TEAM_PHOTOS} emptyIcon={Trophy} emptyLabel="Team photos coming soon" />
          <PanelCaption>
            The people behind Novera — building the agent, the screening pipeline, and the
            physical sensor hardware together, from first prototype to a live product.
          </PanelCaption>
        </motion.div>

        <motion.div variants={staggerItem}>
          <PanelLabel icon={FileText}>Research Paper</PanelLabel>
          <PaperPanel />
          <PanelCaption>
            Our written submission covering the screening approach, the agentic architecture
            behind the WhatsApp Agent, and how human oversight is built into every decision.
          </PanelCaption>
        </motion.div>

        <motion.div variants={staggerItem}>
          <PanelLabel icon={TestTube2}>Product Testing</PanelLabel>
          <ImageSlideshow images={TESTING_PHOTOS} emptyIcon={TestTube2} emptyLabel="Testing photos coming soon" />
          <PanelCaption>
            Real hands-on testing of the physical NOVERA device — capturing saliva samples,
            checking sensor readings, and confirming the WhatsApp experience end to end.
          </PanelCaption>
        </motion.div>
      </motion.div>

      <p className="mt-10 text-center text-sm text-slate-500">
        No stock photos, no mockups — this is the actual team, paper, and hardware behind Novera.
      </p>
    </Section>
  );
}
