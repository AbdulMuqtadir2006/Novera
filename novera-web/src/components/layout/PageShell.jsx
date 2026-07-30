import { motion } from "framer-motion";
import { AmbientBackground } from "../ui/AmbientBackground";

const EASE = [0.16, 1, 0.3, 1];

// Wrapper for every non-home route: animated ambient backdrop, navbar clearance,
// consistent container, and a gentle enter transition.
export function PageShell({ eyebrow, title, intro, children, wide = false }) {
  return (
    <motion.main
      className="relative min-h-dvh pb-28 pt-28 text-depth"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6 }}
      transition={{ duration: 0.3, ease: EASE }}
    >
      <AmbientBackground />
      <div className={`relative z-10 ${wide ? "container-page max-w-7xl" : "container-page"}`}>
        {(eyebrow || title) && (
          <header className="mb-10 max-w-3xl">
            {eyebrow && (
              <motion.p
                className="eyebrow mb-3"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, ease: EASE }}
              >
                {eyebrow}
              </motion.p>
            )}
            {title && (
              <motion.h1
                className="text-balance font-display text-4xl font-bold leading-[1.05] tracking-tight text-depth sm:text-5xl"
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.55, ease: EASE, delay: 0.05 }}
              >
                {title}
              </motion.h1>
            )}
            {intro && (
              <motion.p
                className="mt-4 text-pretty text-lg leading-relaxed text-depth/75"
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.55, ease: EASE, delay: 0.12 }}
              >
                {intro}
              </motion.p>
            )}
          </header>
        )}
        {children}
      </div>
    </motion.main>
  );
}
