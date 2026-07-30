import { Suspense, lazy } from "react";
import { Routes, Route, useLocation } from "react-router-dom";
import { AnimatePresence } from "framer-motion";
import { Navbar } from "./components/layout/Navbar";
import { Footer } from "./components/layout/Footer";
import { ScrollToTop } from "./components/layout/ScrollToTop";
import { RouteFallback } from "./components/ui/RouteFallback";
import { RequireAuth } from "./components/auth/RequireAuth";

// Code-split every route so the homepage doesn't pay for the app bundles.
const Home = lazy(() => import("./pages/Home"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Reports = lazy(() => import("./pages/Reports"));
const Voice = lazy(() => import("./pages/Voice"));
const SelfCare = lazy(() => import("./pages/SelfCare"));
const Appointments = lazy(() => import("./pages/Appointments"));
const ComingSoon = lazy(() => import("./pages/ComingSoon"));
const Login = lazy(() => import("./pages/Login"));
const Signup = lazy(() => import("./pages/Signup"));

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
        <Suspense fallback={<RouteFallback />}>
          <AnimatePresence mode="wait">
            <Routes location={location} key={location.pathname}>
              <Route path="/" element={<Home />} />
              <Route path="/login" element={<Login />} />
              <Route path="/signup" element={<Signup />} />
              <Route path="/dashboard" element={gated(<Dashboard />)} />
              <Route path="/reports" element={gated(<Reports />)} />
              <Route path="/voice" element={gated(<Voice />)} />
              <Route path="/self-care" element={gated(<SelfCare />)} />
              <Route path="/more" element={gated(<Appointments />)} />
              <Route path="*" element={<ComingSoon />} />
            </Routes>
          </AnimatePresence>
        </Suspense>
      </div>
      {!isAuthPage && <Footer />}
    </>
  );
}
