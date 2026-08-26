import { motion } from "framer-motion";
import {
  Activity,
  ArrowDown,
  ArrowRight,
  BarChart3,
  BrainCircuit,
  CheckCircle2,
  Eye,
  GitCompare,
  Hand,
  KeyRound,
  Lock,
  ScrollText,
  ShieldCheck,
  Siren,
  Stethoscope,
  UserCheck,
} from "lucide-react";
import { PageShell } from "../components/layout/PageShell";
import { Reveal, staggerContainer, staggerItem } from "../components/ui/Reveal";

const PIPELINE_STEPS = [
  { icon: Activity, label: "Sensor reading captured" },
  { icon: BarChart3, label: "Scored against fixed clinical reference ranges" },
  { icon: GitCompare, label: "Checked for similarity to real, confirmed prior cases" },
  { icon: BrainCircuit, label: "One narrow AI call picks a result — from that evidence only" },
];

const MECHANISMS = [
  {
    icon: ShieldCheck,
    title: "No hallucination, ever",
    body: "The AI that makes a screening decision is never allowed to invent anything. Its instructions are explicit: use only the evidence it's actually given — never invent a medical threshold, a diagnosis, or a historical case that doesn't exist. If its response ever fails validation, times out, or comes back malformed, nothing is saved. The reading is returned to “needs retest,” never silently replaced with a plausible-sounding guess.",
  },
  {
    icon: BarChart3,
    title: "A reading never jumps straight to a conclusion",
    body: "Every reading is first scored against fixed clinical reference ranges, and separately checked for similarity against a bounded set of real, clinician-confirmed prior cases — both using plain, deterministic math, computed before any AI is even called. Only after that grounding exists does the system make one single, narrow decision call to pick a final result from those pre-computed numbers.",
  },
  {
    icon: Eye,
    title: "The Orchestral AI double-checks before you ever see a result",
    body: "It doesn't just accept whatever the screening decision returns. If a result isn't confident or doesn't pass validation, the case is automatically flagged for human review and marked “retest required” — it is never shown to the patient as if it were real. A deliberate safety override is also active right now: every organ flag is capped at “low risk” system-wide until the physical sensor's own calibration is validated against real clinical data, so unvalidated hardware can never shock a patient with a false alarm.",
  },
  {
    icon: UserCheck,
    title: "Every flagged case goes to a human, never silently decided",
    body: "Nothing about how a result was reached is hidden. Every screening decision — the reading it came from, the score computed for each organ system, and the model's own reasoning — is permanently logged in a full audit trail, and that trail is enforced at the database level: no code path, including a future change, can silently alter or delete a past decision record. A result only ever counts as verified ground truth once a clinician has explicitly reviewed and confirmed it through a dedicated tool; any case the system itself flags as uncertain is preserved for that same manual review — by a clinician or the engineering team — never quietly auto-approved.",
  },
  {
    icon: Siren,
    title: "A hard-coded safety net catches emergencies",
    body: "Before any AI model ever sees a message — on WhatsApp or in the website chat — it's checked against a fixed list of real emergency phrases (chest pain, can't breathe, suicidal thoughts, and similar, in English and Arabic). A match skips the AI entirely and sends an instant, unconditional reply: call Oman's emergency number or go to the nearest ER. This is deterministic pattern-matching, not a model call, deliberately — something this important shouldn't depend on a model behaving as expected in the moment.",
  },
  {
    icon: Hand,
    title: "The AI can offer, but only you can confirm a booking",
    body: "When the system reaches out on its own about a flagged result, it can offer an appointment — but it cannot commit that booking by itself. Booking, cancelling, or rescheduling a real clinic slot only ever happens in direct response to the patient's own reply; the tools that make those real writes are structurally unavailable to every autonomous trigger, not just discouraged by a prompt. An autonomous decision can suggest an action; only a human's own message can commit one.",
  },
  {
    icon: Lock,
    title: "Encryption and data security",
    body: "All traffic between a patient's device, the app, and the backend runs over HTTPS/TLS. Passwords are salted and hashed — never stored, logged, or visible in plain text, not even to us. Every inbound WhatsApp message is cryptographically signature-verified (HMAC) before the system trusts it actually came from Meta and not an impersonator. Every patient's data is scoped strictly to their own account — there is no code path that lets one patient's data leak into another's. Screening decisions, reports, and self-care conversations are processed by third-party AI model providers (OpenRouter, routing to DeepSeek and Anthropic) — only the data needed for that specific request is sent, and it is never sold or shared with anyone beyond what's needed to generate the response.",
  },
  {
    icon: Stethoscope,
    title: "Never a diagnosis",
    body: "Every report, every WhatsApp message, and the physical device itself all say the same thing plainly: this is screening support, not a medical diagnosis. A flagged result always routes toward booking a real clinician appointment — never toward self-treatment or a false sense of certainty.",
  },
];

function PipelineFlow() {
  return (
    <Reveal>
      <div className="rounded-2xl border border-signal/15 bg-paper p-6 sm:p-8">
        <p className="mb-6 text-center font-mono text-xs uppercase tracking-[0.2em] text-depth/45">
          From a reading to a result
        </p>

        <div className="flex flex-col items-center gap-3 lg:flex-row lg:items-stretch lg:justify-between lg:gap-2">
          {PIPELINE_STEPS.map((step, i) => (
            <div key={step.label} className="flex flex-col items-center gap-3 lg:flex-row lg:items-stretch">
              <div className="flex w-full max-w-[220px] flex-col items-center gap-2 rounded-xl border border-depth/10 bg-white/60 px-4 py-4 text-center lg:max-w-[190px]">
                <span className="flex h-9 w-9 items-center justify-center rounded-full border border-signal/25 bg-signal/10 text-signal">
                  <step.icon size={17} strokeWidth={1.75} />
                </span>
                <span className="text-xs font-medium leading-snug text-depth/75">{step.label}</span>
              </div>
              {i < PIPELINE_STEPS.length - 1 && (
                <span className="text-depth/25" aria-hidden="true">
                  <ArrowDown size={18} className="lg:hidden" />
                  <ArrowRight size={18} className="hidden lg:mt-[38px] lg:block" />
                </span>
              )}
            </div>
          ))}
        </div>

        <div className="mx-auto mt-6 flex w-full max-w-[220px] justify-center text-depth/25 lg:max-w-none" aria-hidden="true">
          <ArrowDown size={18} />
        </div>

        <div className="mt-2 grid gap-4 sm:grid-cols-2">
          <div className="flex items-start gap-3 rounded-xl border border-status-good/30 bg-status-good/[0.07] px-4 py-4">
            <CheckCircle2 size={20} className="mt-0.5 shrink-0 text-status-good" strokeWidth={1.75} />
            <p className="text-sm leading-relaxed text-depth/75">
              <span className="font-semibold text-depth">Confident and valid</span> — shown to the
              patient as a real result.
            </p>
          </div>
          <div className="flex items-start gap-3 rounded-xl border border-status-watch/30 bg-status-watch/[0.08] px-4 py-4">
            <ShieldCheck size={20} className="mt-0.5 shrink-0 text-status-watch" strokeWidth={1.75} />
            <p className="text-sm leading-relaxed text-depth/75">
              <span className="font-semibold text-depth">Uncertain or invalid</span> — flagged
              “retest required” and sent for human review. Never shown as a result.
            </p>
          </div>
        </div>
      </div>
    </Reveal>
  );
}

export default function Safety() {
  return (
    <PageShell
      eyebrow="AI Safety & Oversight"
      title="How we keep humans in control"
      intro="The Orchestral AI (WhatsApp) makes real decisions — screening a reading, offering an appointment, reaching out proactively. Every one of those decisions is built around the same rule: the AI can act, but a human can always see, check, and override what it did — and committing to a real booking always waits for the patient's own reply, never the AI's own initiative."
    >
      <PipelineFlow />

      <motion.div
        className="mt-10 grid gap-5 sm:grid-cols-2"
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

      <div className="mt-10 flex items-start gap-3 rounded-2xl border border-depth/10 bg-depth/[0.03] p-6">
        <KeyRound size={20} className="mt-0.5 shrink-0 text-depth/40" strokeWidth={1.75} />
        <p className="text-sm leading-relaxed text-depth/70">
          Novera is a research-stage screening platform. It is built to explore what saliva
          biomarkers can tell us — not to diagnose, treat, or replace care from a medical
          professional.
        </p>
      </div>

      <div className="mt-6 flex items-start gap-3 rounded-2xl border border-depth/10 bg-depth/[0.03] p-6">
        <ScrollText size={20} className="mt-0.5 shrink-0 text-depth/40" strokeWidth={1.75} />
        <p className="text-sm leading-relaxed text-depth/70">
          Every mechanism on this page is grounded in the actual code that runs in production —
          this is a description of what the system does, not an aspiration.
        </p>
      </div>
    </PageShell>
  );
}
