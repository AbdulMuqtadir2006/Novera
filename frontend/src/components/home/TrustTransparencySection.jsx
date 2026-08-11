import { motion } from "framer-motion";
import {
  ShieldCheck, ClipboardList, Ban, Sparkles, Stethoscope, Database,
  Radar, GitCompareArrows, MessageSquareText, Compass, UserCheck,
} from "lucide-react";
import { Section } from "./Section";
import { staggerContainer, staggerItem } from "../ui/Reveal";
import { useLang } from "../../i18n/LanguageContext";

const PIPELINE_STEPS = [
  { id: "capture", icon: Radar, titleKey: "trust.stepCapture", detailKey: "trust.stepCaptureDetail" },
  { id: "analysis", icon: GitCompareArrows, titleKey: "trust.stepAnalysis", detailKey: "trust.stepAnalysisDetail" },
  { id: "insight", icon: MessageSquareText, titleKey: "trust.stepInsight", detailKey: "trust.stepInsightDetail" },
  { id: "guidance", icon: Compass, titleKey: "trust.stepGuidance", detailKey: "trust.stepGuidanceDetail" },
  { id: "clinician", icon: UserCheck, titleKey: "trust.stepClinician", detailKey: "trust.stepClinicianDetail" },
];

function TrustCard({ icon: Icon, title, children }) {
  return (
    <motion.div variants={staggerItem} className="glass-card h-full p-6">
      <span className="flex h-12 w-12 items-center justify-center rounded-xl border border-white/10 bg-white/5 text-signal">
        <Icon size={22} strokeWidth={1.75} />
      </span>
      <h3 className="mt-5 font-display text-lg font-semibold text-white">{title}</h3>
      <div className="mt-2 space-y-3 text-sm leading-relaxed text-slate-400">{children}</div>
    </motion.div>
  );
}

function TrustPipeline({ t }) {
  return (
    <div className="glass-card mt-10 p-5 sm:p-6">
      <p className="font-mono text-xs uppercase tracking-[0.2em] text-signal">{t("trust.pipelineTitle")}</p>
      <p className="mt-2 text-sm text-slate-400">{t("trust.pipelineIntro")}</p>
      <div className="mt-6 overflow-x-auto pb-1">
        <div className="flex w-max min-w-full items-start">
          {PIPELINE_STEPS.map((step, i) => (
            <div key={step.id} className="flex items-start">
              <div className="flex w-24 flex-col items-center gap-2 text-center sm:w-28">
                <span
                  className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full border-2 ${
                    step.id === "clinician"
                      ? "border-status-good/70 bg-status-good/10 text-status-good"
                      : "border-signal/60 bg-signal/10 text-signal"
                  }`}
                >
                  <step.icon size={18} />
                </span>
                <span className="text-xs font-semibold text-white">{t(step.titleKey)}</span>
                <span className="text-[11px] leading-tight text-slate-500">{t(step.detailKey)}</span>
              </div>
              {i < PIPELINE_STEPS.length - 1 && (
                <div className="mx-1 mt-[22px] h-0.5 min-w-[20px] flex-1 rounded-full bg-white/10 sm:min-w-[32px]" />
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// Homepage section making the backend's real safety engineering (audit
// trail, no-fabrication guarantee, AI/fallback tagging, human-in-the-loop
// handoff) visible in the product itself — see backend/app/core/scoring.py,
// screening_llm.py, content_llm.py/fallbacks.py, whatsapp_agent.py, booking.py.
export function TrustTransparencySection() {
  const { t } = useLang();

  return (
    <Section
      id="trust"
      eyebrow={t("trust.eyebrow")}
      title={t("trust.title")}
      intro={t("trust.intro")}
    >
      <motion.div
        className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3"
        variants={staggerContainer}
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: "0px 0px -15% 0px" }}
      >
        <TrustCard icon={ShieldCheck} title={t("trust.whatTitle")}>
          <p>{t("trust.whatBody")}</p>
        </TrustCard>

        <TrustCard icon={ClipboardList} title={t("trust.auditTitle")}>
          <p>{t("trust.auditBody")}</p>
          <div className="flex flex-wrap gap-2 pt-1">
            {["trust.auditChipModel", "trust.auditChipScores", "trust.auditChipReasoning"].map((key) => (
              <span
                key={key}
                className="inline-flex items-center rounded-full border border-signal/25 bg-signal/5 px-3 py-1 text-xs font-medium text-slate-300"
              >
                {t(key)}
              </span>
            ))}
          </div>
        </TrustCard>

        <TrustCard icon={Ban} title={t("trust.noFabTitle")}>
          <p>{t("trust.noFabBody")}</p>
        </TrustCard>

        <TrustCard icon={Sparkles} title={t("trust.badgeTitle")}>
          <p>{t("trust.badgeBody")}</p>
          <div className="flex flex-wrap gap-2 pt-1">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-signal/10 px-2.5 py-1 font-mono text-[10px] uppercase tracking-wide text-signal">
              <Sparkles size={11} /> {t("reports.aiBadge")}
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-signal/10 px-2.5 py-1 font-mono text-[10px] uppercase tracking-wide text-signal">
              <Sparkles size={11} /> {t("reports.fallbackBadge")}
            </span>
          </div>
        </TrustCard>

        <TrustCard icon={Stethoscope} title={t("trust.humanTitle")}>
          <p>{t("trust.humanBody")}</p>
        </TrustCard>

        <TrustCard icon={Database} title={t("trust.dataTitle")}>
          <p>{t("trust.dataBody")}</p>
        </TrustCard>
      </motion.div>

      <TrustPipeline t={t} />
    </Section>
  );
}
