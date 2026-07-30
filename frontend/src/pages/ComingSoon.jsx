import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import { Compass, ArrowLeft } from "lucide-react";
import { PageShell } from "../components/layout/PageShell";
import { useLang } from "../i18n/LanguageContext";

export default function ComingSoon() {
  const { t } = useLang();
  return (
    <PageShell>
      <div className="flex min-h-[60vh] flex-col items-center justify-center text-center">
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          className="relative flex h-24 w-24 items-center justify-center"
        >
          <span className="absolute inset-0 animate-pulse-ring rounded-full border border-signal/40" />
          <span className="relative flex h-24 w-24 items-center justify-center rounded-full border border-signal/25 bg-paper text-signal shadow-card">
            <Compass size={38} strokeWidth={1.5} />
          </span>
        </motion.div>

        <motion.h1
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="mt-8 font-display text-3xl font-bold text-depth sm:text-4xl"
        >
          {t("more.title")}
        </motion.h1>
        <motion.p
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.18 }}
          className="mt-4 max-w-md text-pretty text-depth/60"
        >
          {t("more.body")}
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.26 }}
        >
          <Link
            to="/dashboard"
            className="mt-8 inline-flex items-center gap-2 rounded-full border border-depth/15 bg-paper px-6 py-3 font-semibold text-depth transition duration-200 hover:border-signal/50 hover:text-depth"
          >
            <ArrowLeft size={18} /> {t("more.back")}
          </Link>
        </motion.div>
      </div>
    </PageShell>
  );
}
