import { motion } from "framer-motion";
import {
  ShieldCheck,
  UserCheck,
  ScrollText,
  SlidersHorizontal,
  Stethoscope,
  Lock,
} from "lucide-react";
import { PageShell } from "../components/layout/PageShell";
import { staggerContainer, staggerItem } from "../components/ui/Reveal";

const MECHANISMS = [
  {
    icon: ShieldCheck,
    title: "No-fabrication guarantee",
    body: "If the AI screening call fails, times out, or returns anything invalid, the system never falls back to a guess. The case is returned to \"needs retest\" and nothing gets saved — no result is ever shown that didn't come from a real, validated model response.",
  },
  {
    icon: UserCheck,
    title: "Human sign-off required",
    body: "An AI screening result never counts as verified ground truth on its own. A clinician must explicitly review and confirm a case through a dedicated tool before it's treated as real — the AI never grades its own homework.",
  },
  {
    icon: ScrollText,
    title: "Full decision audit trail",
    body: "Every single screening decision — the reading it came from, the score computed for each organ system, and the model's final reasoning — is permanently logged. Nothing about how a result was reached is hidden or discarded.",
  },
  {
    icon: SlidersHorizontal,
    title: "A hardware safety switch",
    body: "Until the physical sensor's calibration is validated against real clinical data, a deliberate override forces every organ flag down to \"low risk\" — the system will not let unvalidated hardware tell someone they may be sick.",
  },
  {
    icon: Stethoscope,
    title: "Never a diagnosis",
    body: "Every report, message, and the physical device itself is explicit: this is screening support, not a medical diagnosis, and a flagged result always routes toward booking a real clinician — never toward self-treatment.",
  },
  {
    icon: Lock,
    title: "Data security basics, done properly",
    body: "Passwords are salted and hashed, never stored in plain text. Every inbound WhatsApp message is cryptographically signature-verified before it's trusted. Access to a patient's data is scoped strictly to their own account.",
  },
];

export default function Safety() {
  return (
    <PageShell
      eyebrow="AI Safety & Oversight"
      title="How we keep humans in control"
      intro="Novera's agent makes real decisions — screening a reading, booking an appointment, reaching out proactively. Every one of those decisions is built around the same rule: the AI can act, but a human can always see, check, and override what it did."
    >
      <motion.div
        className="grid gap-5 sm:grid-cols-2"
        variants={staggerContainer}
        initial="hidden"
        animate="show"
      >
        {MECHANISMS.map(({ icon: Icon, title, body }) => (
          <motion.div
            key={title}
            variants={staggerItem}
            className="rounded-2xl border border-signal/15 bg-paper p-6"
          >
            <div className="inline-flex h-11 w-11 items-center justify-center rounded-xl border border-signal/25 bg-signal/10 text-signal">
              <Icon size={20} strokeWidth={1.75} />
            </div>
            <h3 className="mt-4 font-display text-lg font-semibold text-depth">{title}</h3>
            <p className="mt-2 text-sm leading-relaxed text-depth/70">{body}</p>
          </motion.div>
        ))}
      </motion.div>

      <div className="mt-10 rounded-2xl border border-depth/10 bg-depth/[0.03] p-6">
        <p className="text-sm leading-relaxed text-depth/70">
          Novera is a research-stage screening platform. It is built to explore what saliva
          biomarkers can tell us — not to diagnose, treat, or replace care from a medical
          professional.
        </p>
      </div>
    </PageShell>
  );
}
