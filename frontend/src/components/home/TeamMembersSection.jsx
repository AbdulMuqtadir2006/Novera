import { useState } from "react";
import { motion } from "framer-motion";
import { User } from "lucide-react";
import { Section } from "./Section";
import { staggerContainer, staggerItem } from "../ui/Reveal";
import { TEAM_MEMBERS } from "../../data/team";

// Never a broken-image icon (2026-08-25) — matches ImageSlideshow's own
// "honest placeholder, not a broken image" rule. Falls back to a plain
// person glyph until the real portrait is dropped into public/team/.
function MemberPhoto({ src, alt }) {
  const [failed, setFailed] = useState(false);
  if (failed) {
    return (
      <div className="flex aspect-[4/5] w-full items-center justify-center bg-depth/5 text-depth/20">
        <User size={48} strokeWidth={1.25} />
      </div>
    );
  }
  return (
    <img
      src={src}
      alt={alt}
      onError={() => setFailed(true)}
      className="aspect-[4/5] w-full object-cover object-top transition-transform duration-500 ease-expo group-hover:scale-[1.04]"
    />
  );
}

function MemberCard({ member }) {
  return (
    <motion.div
      variants={staggerItem}
      whileHover={{ y: -6 }}
      transition={{ type: "spring", stiffness: 300, damping: 22 }}
      className="group flex h-full flex-col overflow-hidden rounded-2xl border border-depth/10 bg-paper shadow-card transition-shadow duration-300 hover:shadow-lift"
    >
      <MemberPhoto src={member.photo} alt={member.name} />
      <div className="flex flex-1 flex-col p-7">
        <h3 className="font-display text-lg font-bold text-depth">{member.name}</h3>
        <p className="mt-1 text-sm font-medium text-depth/55">{member.role}</p>
        <p className="mt-3 text-sm leading-relaxed text-depth/70">{member.description}</p>
      </div>
    </motion.div>
  );
}

// "Meet the Team" (2026-08-25) — sits right after the "Behind Novera"
// showcase. Deliberately light cards (bg-paper) on the dark homepage, per
// Hassan's own spec: clean, minimal, no gradients/tags/stats/icons beyond
// the portrait itself.
export function TeamMembersSection() {
  return (
    <Section
      id="team"
      eyebrow="The Team"
      title="Meet the people behind Novera."
      intro="Three disciplines, one product — engineering, hardware, and business working together."
    >
      <motion.div
        className="grid gap-6 sm:grid-cols-3"
        variants={staggerContainer}
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: "0px 0px -15% 0px" }}
      >
        {TEAM_MEMBERS.map((member) => (
          <MemberCard key={member.name} member={member} />
        ))}
      </motion.div>
    </Section>
  );
}
