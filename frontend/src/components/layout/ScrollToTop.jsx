import { useEffect } from "react";
import { useLocation } from "react-router-dom";

// Reset scroll on route change (except when returning to a hash target).
// Hash targets (e.g. Footer's Privacy link -> "/#trust") are handled with a
// short poll rather than a single scrollIntoView: the destination route is
// lazy-loaded (see App.jsx), so the element often doesn't exist in the DOM
// yet on the frame this effect first runs.
export function ScrollToTop() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (hash) {
      const id = hash.slice(1);
      let attempts = 0;
      let timer;
      const tryScroll = () => {
        const el = document.getElementById(id);
        if (el) {
          el.scrollIntoView({ behavior: "smooth", block: "start" });
          return;
        }
        if (attempts++ < 30) timer = setTimeout(tryScroll, 100);
      };
      tryScroll();
      return () => clearTimeout(timer);
    }
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [pathname, hash]);
  return null;
}
