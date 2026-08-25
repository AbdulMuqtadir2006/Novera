import { useState } from "react";
import { motion } from "framer-motion";
import { User } from "lucide-react";
import { staggerContainer, staggerItem } from "../ui/Reveal";
import { TEAM_MEMBERS } from "../../data/team";

// Never a broken-image icon (2026-08-25) — matches ImageSlideshow's own
// "honest placeholder, not a broken image" rule. Falls back to a plain
// person glyph until the real portrait is dropped into public/team/.
function MemberPhoto({ src, alt }) {
  const [failed, setFailed] = useState(false);
  if (failed) {
    return (
      <div className="flex aspect-[4/5] w-full items-center justify-center bg-white/[0.03] text-white/15">
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

// glass-card (2026-08-25, fix) — the light bg-paper/text-depth treatment
// this used at first is the site's *light-page* card style (see .light-card
// in index.css, only ever used on Dashboard/Reports/Buy/SelfCare etc.) and
// looked out of place dropped onto the dark homepage. Switched to the same
// dark translucent glass-card + signal-accent language every other homepage
// card already uses (AgentsSection's AgentCard, HealthAreasSection, ...).
function MemberCard({ member }) {
  return (
    <motion.div
      variants={staggerItem}
      whileHover={{ y: -6 }}
      transition={{ type: "spring", stiffness: 300, damping: 22 }}
      className="glass-card group flex h-full flex-col overflow-hidden transition-colors duration-300 hover:border-signal/40"
    >
      <MemberPhoto src={member.photo} alt={member.name} />
      <div className="flex flex-1 flex-col p-7">
        <h3 className="font-display text-lg font-bold text-white">{member.name}</h3>
        <p className="mt-1 text-sm font-medium text-signal">{member.role}</p>
        <p className="mt-3 text-sm leading-relaxed text-slate-400">{member.description}</p>
      </div>
    </motion.div>
  );
}

// "Meet the Team" (2026-08-25) — sits right after the "Behind Novera"
// showcase, deliberately close to it: a small top padding and a plain bold
// heading instead of the shared Section component's eyebrow/title/intro
// treatment, so the two photo groups read as one continuous "behind the
// scenes" block rather than two separate, far-apart homepage sections. Dark
// glass cards matching the rest of the homepage; clean and minimal per
// Hassan's own spec — no gradients/tags/stats/icons beyond the portrait.
export function TeamMembersSection() {
  return (
    <section id="team" className="relative pb-24 pt-4 sm:pb-32 sm:pt-8">
      <div className="container-page">
        <h2 className="mb-8 text-center font-display text-2xl font-bold text-white sm:text-3xl">
          The Team
        </h2>
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
      </div>
    </section>
  );
}
