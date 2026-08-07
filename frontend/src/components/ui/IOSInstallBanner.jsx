import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Share, X } from "lucide-react";
import { useLang } from "../../i18n/LanguageContext";

const DISMISS_KEY = "novera-ios-install-dismissed";

// iOS gives no API to trigger "Add to Home Screen" programmatically — the
// most we can do is make the manual step (Share -> Add to Home Screen)
// unmissable the moment someone lands here in Safari and hasn't installed
// it yet.
function isIOSSafariNotInstalled() {
  if (typeof window === "undefined" || typeof navigator === "undefined") return false;
  const isIOS =
    /iphone|ipad|ipod/i.test(navigator.userAgent) ||
    // iPadOS 13+ reports its UA as a Mac but is touch-capable, unlike a real Mac.
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const isStandalone =
    window.navigator.standalone === true || window.matchMedia("(display-mode: standalone)").matches;
  return isIOS && !isStandalone;
}

/** Bottom-anchored toast pointing iOS Safari visitors at the Share -> Add to
 * Home Screen flow. Dismissible per session; reappears on a fresh visit. */
export function IOSInstallBanner() {
  const { t } = useLang();
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (sessionStorage.getItem(DISMISS_KEY)) return;
    if (isIOSSafariNotInstalled()) setVisible(true);
  }, []);

  const dismiss = () => {
    sessionStorage.setItem(DISMISS_KEY, "1");
    setVisible(false);
  };

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ y: 80, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 80, opacity: 0 }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
          className="glass-card fixed inset-x-4 bottom-[calc(1rem+env(safe-area-inset-bottom))] z-[60] flex items-center gap-3 border-signal/20 bg-ink/95 p-4 shadow-lift sm:inset-x-auto sm:right-4 sm:w-96"
          role="status"
        >
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-signal/15 text-signal">
            <Share size={18} />
          </span>
          <div className="flex-1">
            <p className="font-display text-sm font-semibold text-white">{t("install.iosTitle")}</p>
            <p className="mt-0.5 text-xs leading-relaxed text-slate-300">{t("install.iosBody")}</p>
          </div>
          <button
            type="button"
            onClick={dismiss}
            aria-label={t("install.dismiss")}
            className="shrink-0 rounded-full p-1.5 text-slate-400 transition hover:bg-white/10 hover:text-white"
          >
            <X size={16} />
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
