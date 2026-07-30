import { ArrowRight } from "lucide-react";
import { Reveal } from "../ui/Reveal";
import { MagneticButton } from "../ui/MagneticButton";
import { useLang } from "../../i18n/LanguageContext";

export function CtaSection() {
  const { t } = useLang();
  return (
    <section className="relative overflow-hidden py-28 sm:py-36">
      {/* Ambient glow */}
      <div
        className="pointer-events-none absolute left-1/2 top-1/2 h-[520px] w-[520px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-signal/10 blur-[120px]"
        aria-hidden="true"
      />
      <div className="container-page relative text-center">
        {/* Research note — quiet, footer-adjacent */}
        <Reveal>
          <p className="mx-auto mb-14 max-w-2xl text-pretty text-sm leading-relaxed text-slate-500">
            Novera is a research-stage screening platform, built to explore what
            saliva biomarkers can tell us — not to diagnose, treat, or replace
            care from a medical professional.
          </p>
        </Reveal>

        <Reveal delay={0.05}>
          <h2 className="mx-auto max-w-3xl text-balance font-display text-4xl font-extrabold leading-tight text-white sm:text-5xl md:text-6xl">
            {t("cta.title")}
          </h2>
        </Reveal>
        <Reveal delay={0.15}>
          <div className="mt-10 flex justify-center">
            <MagneticButton to="/dashboard">
              {t("cta.button")}
              <ArrowRight size={18} />
            </MagneticButton>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
