import { Suspense, lazy } from "react";
import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AnimatePresence } from "framer-motion";
import { Navbar } from "./components/layout/Navbar";
import { Footer } from "./components/layout/Footer";
import { ScrollToTop } from "./components/layout/ScrollToTop";
import { RouteFallback } from "./components/ui/RouteFallback";
import { RouteErrorBoundary } from "./components/ui/RouteErrorBoundary";
import { IOSInstallBanner } from "./components/ui/IOSInstallBanner";
import { RequireAuth } from "./components/auth/RequireAuth";

// Code-split every route so the homepage doesn't pay for the app bundles.
// Voice.jsx and Appointments.jsx are intentionally left unwired here (not
// deleted) — both features are paused for now, not removed. See git history
// for the routes that used to point at them (/voice, /more) if either needs
// to come back.
const Home = lazy(() => import("./pages/Home"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Reports = lazy(() => import("./pages/Reports"));
const SelfCare = lazy(() => import("./pages/SelfCare"));
const ComingSoon = lazy(() => import("./pages/ComingSoon"));
const Login = lazy(() => import("./pages/Login"));
const Signup = lazy(() => import("./pages/Signup"));
const Buy = lazy(() => import("./pages/Buy"));
const OrderConfirmation = lazy(() => import("./pages/OrderConfirmation"));

const gated = (el) => <RequireAuth>{el}</RequireAuth>;

export default function App() {
  const location = useLocation();
  const isAuthPage = location.pathname === "/login" || location.pathname === "/signup";

  return (
    <>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:rounded-full focus:bg-vital focus:px-5 focus:py-2 focus:font-semibold focus:text-white"
      >
        Skip to content
      </a>
      <ScrollToTop />
      {!isAuthPage && <Navbar />}
      <div id="main">
        {/* Keyed by pathname: if a page crashes, navigating to a different
            route remounts the boundary fresh instead of staying stuck —
            Navbar/Footer live outside it so nav is always still clickable. */}
        <RouteErrorBoundary key={location.pathname}>
          <Suspense fallback={<RouteFallback />}>
            <AnimatePresence mode="wait">
              <Routes location={location} key={location.pathname}>
                <Route path="/" element={<Home />} />
                <Route path="/login" element={<Login />} />
                <Route path="/signup" element={<Signup />} />
                <Route path="/dashboard" element={gated(<Dashboard />)} />
                <Route path="/reports" element={gated(<Reports />)} />
                <Route path="/self-care" element={gated(<SelfCare />)} />
                <Route path="/buy" element={<Buy />} />
                <Route path="/order/:token" element={<OrderConfirmation />} />
                {/* /subscription was a placeholder before the pivot to one-time
                    device/bundle pricing — redirect any old links/bookmarks. */}
                <Route path="/subscription" element={<Navigate to="/buy" replace />} />
                <Route path="*" element={<ComingSoon />} />
              </Routes>
            </AnimatePresence>
          </Suspense>
        </RouteErrorBoundary>
      </div>
      {!isAuthPage && <Footer />}
      <IOSInstallBanner />
    </>
  );
}
