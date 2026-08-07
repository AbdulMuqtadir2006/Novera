import { useEffect, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Menu, X, Languages, LogOut, LogIn } from "lucide-react";
import { navLinks } from "./navLinks";
import { Wordmark } from "../ui/Wordmark";
import { useLang } from "../../i18n/LanguageContext";
import { useAuth } from "../../auth/AuthContext";

const EASE = [0.16, 1, 0.3, 1];

function AuthControl({ overDark }) {
  const { t } = useLang();
  const { user, logout } = useAuth();
  const idle = overDark
    ? "border-white/20 text-white/80 hover:border-signal/50 hover:text-white"
    : "border-depth/15 text-depth/80 hover:border-signal/50 hover:text-depth";
  if (user) {
    return (
      <div className="flex items-center gap-2">
        <span className={`hidden text-sm font-medium lg:inline ${overDark ? "text-white/70" : "text-depth/70"}`}>
          {t("auth.hello")}, {user.name?.split(" ")[0] || user.email}
        </span>
        <button
          type="button"
          onClick={logout}
          className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium transition-colors duration-200 ${idle}`}
        >
          <LogOut size={15} /> {t("auth.logout")}
        </button>
      </div>
    );
  }
  return (
    <Link
      to="/login"
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium transition-colors duration-200 ${idle}`}
    >
      <LogIn size={15} /> {t("auth.login")}
    </Link>
  );
}

function LangToggle({ overDark }) {
  const { toggle, t } = useLang();
  return (
    <button
      type="button"
      onClick={toggle}
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium transition-colors duration-200 ${
        overDark
          ? "border-white/20 text-white/80 hover:border-signal/50 hover:text-white"
          : "border-depth/15 text-depth/80 hover:border-signal/50 hover:text-depth"
      }`}
      aria-label={t("common.language")}
    >
      <Languages size={16} />
      {t("lang.toggle")}
    </button>
  );
}

function DesktopLinks({ overDark }) {
  const { t } = useLang();
  const base = overDark ? "text-white/70" : "text-depth/70";
  const active = overDark ? "text-white" : "text-depth";
  const pill = overDark ? "bg-white/10" : "bg-signal/12";

  return (
    <ul className="relative hidden items-center gap-1 md:flex">
      {navLinks.map((link) => (
        <li key={link.to} className="relative">
          <NavLink
            to={link.to}
            end={link.to === "/"}
            className={({ isActive }) =>
              `relative inline-flex items-center rounded-full px-4 py-2 text-sm font-medium transition-colors duration-200 ${
                isActive ? active : base
              }`
            }
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <motion.span
                    layoutId="nav-pill"
                    className={`absolute inset-0 -z-10 rounded-full ${pill}`}
                    transition={{ type: "spring", stiffness: 380, damping: 32 }}
                  />
                )}
                {t(link.key)}
              </>
            )}
          </NavLink>
        </li>
      ))}
    </ul>
  );
}

export function Navbar() {
  const { pathname } = useLocation();
  const { t } = useLang();
  const isHome = pathname === "/";
  const [open, setOpen] = useState(false);

  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  useEffect(() => setOpen(false), [pathname]);

  // Home: transparent throughout (the whole page is dark ink). Subpages: solid paper.
  const overDark = isHome;
  const headerClass = isHome
    ? "bg-transparent border-transparent"
    : "bg-paper/90 backdrop-blur-md border-signal/10";
  const menuColor = isHome ? "text-white" : "text-depth";

  return (
    <>
      <header
        className={`fixed inset-x-0 top-0 z-50 border-b pt-safe transition-colors duration-300 ease-expo ${headerClass}`}
      >
        <nav className="container-page flex h-16 items-center justify-between">
          <Link to="/" aria-label="Novera home" className="shrink-0">
            <Wordmark tone={overDark ? "light" : "dark"} />
          </Link>

          <div className="flex items-center gap-3">
            <DesktopLinks overDark={overDark} />
            <div className="hidden items-center gap-3 md:flex">
              <LangToggle overDark={overDark} />
              <AuthControl overDark={overDark} />
            </div>
            <button
              type="button"
              className={`inline-flex h-11 w-11 items-center justify-center rounded-full md:hidden ${menuColor}`}
              aria-label={open ? "Close menu" : "Open menu"}
              aria-expanded={open}
              onClick={() => setOpen((v) => !v)}
            >
              {open ? <X size={24} /> : <Menu size={24} />}
            </button>
          </div>
        </nav>
      </header>

      <AnimatePresence>
        {open && (
          <motion.div
            className="fixed inset-0 z-40 flex flex-col bg-ink/95 pb-safe pt-safe backdrop-blur-2xl md:hidden"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
          >
            <div className="mt-16 flex flex-1 flex-col justify-center gap-1 px-8">
              {navLinks.map((link, i) => (
                <motion.div
                  key={link.to}
                  initial={{ opacity: 0, x: -24 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -12 }}
                  transition={{ delay: 0.06 * i + 0.05, duration: 0.4, ease: EASE }}
                >
                  <NavLink
                    to={link.to}
                    end={link.to === "/"}
                    className={({ isActive }) =>
                      `block border-b border-white/10 py-4 font-display text-3xl font-semibold transition-colors ${
                        isActive ? "text-signal" : "text-white/90"
                      }`
                    }
                  >
                    {t(link.key)}
                  </NavLink>
                </motion.div>
              ))}
              <div className="mt-8 flex items-center gap-3">
                <LangToggle overDark={true} />
                <AuthControl overDark={true} />
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
