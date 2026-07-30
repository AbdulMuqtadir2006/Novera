import { useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { motion } from "framer-motion";
import { Loader2, CircleAlert } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { useLang } from "../i18n/LanguageContext";
import { Wordmark } from "../components/ui/Wordmark";

export default function Login() {
  const { t } = useLang();
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from || "/dashboard";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err.message || "Login failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="relative flex min-h-dvh items-center justify-center overflow-hidden bg-ink px-5 py-24">
      <div className="pointer-events-none absolute -left-40 top-1/4 h-[420px] w-[420px] animate-drift-a rounded-full bg-vital/10 blur-[120px]" aria-hidden="true" />
      <div className="pointer-events-none absolute -right-40 bottom-1/4 h-[420px] w-[420px] animate-drift-b rounded-full bg-signal/10 blur-[120px]" aria-hidden="true" />

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className="relative w-full max-w-md"
      >
        <div className="mb-8 flex justify-center">
          <Link to="/"><Wordmark tone="light" /></Link>
        </div>
        <div className="glass-card p-8">
          <h1 className="font-display text-2xl font-bold text-white">{t("auth.loginTitle")}</h1>
          <p className="mt-1 text-sm text-slate-400">{t("auth.loginSub")}</p>

          <form onSubmit={submit} className="mt-6 space-y-4">
            <Field label={t("auth.email")} type="email" value={email} onChange={setEmail} autoComplete="email" required />
            <Field label={t("auth.password")} type="password" value={password} onChange={setPassword} autoComplete="current-password" required />

            {error && (
              <p className="flex items-center gap-2 text-sm text-status-attention">
                <CircleAlert size={16} /> {error}
              </p>
            )}

            <button type="submit" disabled={busy} className="btn-primary w-full disabled:opacity-60">
              {busy ? <Loader2 size={18} className="animate-spin" /> : null}
              {busy ? t("auth.working") : t("auth.submitLogin")}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-slate-400">
            {t("auth.noAccount")}{" "}
            <Link to="/signup" className="font-semibold text-signal hover:underline">{t("auth.signup")}</Link>
          </p>
        </div>
      </motion.div>
    </main>
  );
}

export function Field({ label, type = "text", value, onChange, hint, ...rest }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-slate-300">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-white placeholder-slate-500 outline-none transition focus:border-signal/60"
        {...rest}
      />
      {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
    </label>
  );
}
