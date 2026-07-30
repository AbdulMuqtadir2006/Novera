import { useEffect } from "react";
import { useLocation } from "react-router-dom";

// Reset scroll on route change (except when returning to a hash target).
export function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [pathname]);
  return null;
}
