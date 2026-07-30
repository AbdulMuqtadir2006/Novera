import { Reveal } from "../ui/Reveal";

// Dark homepage section wrapper with an optional heading block.
export function Section({ id, eyebrow, title, intro, children, className = "" }) {
  return (
    <section id={id} className={`relative py-24 sm:py-32 ${className}`}>
      <div className="container-page">
        {(eyebrow || title) && (
          <div className="mb-14 max-w-2xl">
            {eyebrow && (
              <Reveal>
                <p className="eyebrow mb-4">{eyebrow}</p>
              </Reveal>
            )}
            {title && (
              <Reveal delay={0.05}>
                <h2 className="text-balance font-display text-3xl font-bold leading-tight text-white sm:text-4xl md:text-[2.75rem]">
                  {title}
                </h2>
              </Reveal>
            )}
            {intro && (
              <Reveal delay={0.1}>
                <p className="mt-5 text-pretty text-base leading-relaxed text-slate-400 sm:text-lg">
                  {intro}
                </p>
              </Reveal>
            )}
          </div>
        )}
        {children}
      </div>
    </section>
  );
}
