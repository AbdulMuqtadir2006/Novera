import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Loader2, CircleAlert } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { useLang } from "../i18n/LanguageContext";
import { Wordmark } from "../components/ui/Wordmark";
import { Field } from "./Login";

export default function Signup() {
  const { t } = useLang();
  const { signup } = useAuth();
  const navigate = useNavigate();

  const [form, setForm] = useState({ name: "", email: "", phone: "+968", password: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await signup(form);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(err.message || "Signup failed");
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
          <h1 className="font-display text-2xl font-bold text-white">{t("auth.signupTitle")}</h1>
          <p className="mt-1 text-sm text-slate-400">{t("auth.signupSub")}</p>

          <form onSubmit={submit} className="mt-6 space-y-4">
            <Field label={t("auth.name")} value={form.name} onChange={set("name")} autoComplete="name" required />
            <Field label={t("auth.email")} type="email" value={form.email} onChange={set("email")} autoComplete="email" required />
            <Field label={t("auth.phone")} type="tel" value={form.phone} onChange={set("phone")} hint={t("auth.phoneHint")} autoComplete="tel" required />
            <Field label={t("auth.password")} type="password" value={form.password} onChange={set("password")} autoComplete="new-password" required />

            {error && (
              <p className="flex items-center gap-2 text-sm text-status-attention">
                <CircleAlert size={16} /> {error}
              </p>
            )}

            <button type="submit" disabled={busy} className="btn-primary w-full disabled:opacity-60">
              {busy ? <Loader2 size={18} className="animate-spin" /> : null}
              {busy ? t("auth.working") : t("auth.submitSignup")}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-slate-400">
            {t("auth.haveAccount")}{" "}
            <Link to="/login" className="font-semibold text-signal hover:underline">{t("auth.login")}</Link>
          </p>
        </div>
      </motion.div>
    </main>
  );
}
