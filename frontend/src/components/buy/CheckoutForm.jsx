import { useState } from "react";
import { CircleAlert, Loader2, Lock } from "lucide-react";
import { useLang } from "../../i18n/LanguageContext";

const EMPTY = {
  email: "",
  phone: "",
  full_name: "",
  line1: "",
  line2: "",
  city: "",
  governorate: "",
  postal_code: "",
  country: "Oman",
};

function Field({ id, label, value, onChange, required = true, type = "text" }) {
  return (
    <label htmlFor={id} className="block">
      <span className="mb-1.5 block text-xs font-medium text-depth/60">{label}</span>
      <input
        id={id}
        type={type}
        required={required}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-xl border border-depth/15 bg-paper px-4 py-2.5 text-sm text-depth outline-none transition placeholder:text-depth/35 focus:border-signal"
      />
    </label>
  );
}

// §3 checkout form: standard cart fields (contact + shipping address), no
// account required (guest checkout — see routers/orders.py). Submitting
// hands a flat payload to the parent, which owns the actual checkout() API
// call and redirect to Thawani, since the parent also knows the cart items.
export function CheckoutForm({ onSubmit, submitting, error }) {
  const { t } = useLang();
  const [form, setForm] = useState(EMPTY);
  const set = (key) => (value) => setForm((f) => ({ ...f, [key]: value }));

  const handleSubmit = (e) => {
    e.preventDefault();
    onSubmit({
      email: form.email,
      phone: form.phone,
      shipping_address: {
        full_name: form.full_name,
        line1: form.line1,
        line2: form.line2,
        city: form.city,
        governorate: form.governorate,
        postal_code: form.postal_code,
        country: form.country,
      },
    });
  };

  return (
    <form onSubmit={handleSubmit} className="mt-6 space-y-4 border-t border-depth/10 pt-6">
      <h3 className="font-display text-base font-semibold text-depth">{t("buy.checkout.title")}</h3>

      <div className="grid grid-cols-2 gap-3">
        <Field id="co-email" label={t("buy.checkout.email")} type="email" value={form.email} onChange={set("email")} />
        <Field id="co-phone" label={t("buy.checkout.phone")} type="tel" value={form.phone} onChange={set("phone")} />
      </div>
      <Field id="co-name" label={t("buy.checkout.fullName")} value={form.full_name} onChange={set("full_name")} />
      <Field id="co-line1" label={t("buy.checkout.line1")} value={form.line1} onChange={set("line1")} />
      <Field id="co-line2" label={t("buy.checkout.line2")} required={false} value={form.line2} onChange={set("line2")} />
      <div className="grid grid-cols-2 gap-3">
        <Field id="co-city" label={t("buy.checkout.city")} value={form.city} onChange={set("city")} />
        <Field id="co-gov" label={t("buy.checkout.governorate")} required={false} value={form.governorate} onChange={set("governorate")} />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field id="co-postal" label={t("buy.checkout.postalCode")} required={false} value={form.postal_code} onChange={set("postal_code")} />
        <Field id="co-country" label={t("buy.checkout.country")} value={form.country} onChange={set("country")} />
      </div>

      {error && (
        <p className="flex items-center gap-2 text-sm font-medium text-status-attention">
          <CircleAlert size={16} /> {error}
        </p>
      )}

      <button type="submit" disabled={submitting} className="btn-primary w-full disabled:opacity-60">
        {submitting ? <Loader2 size={18} className="animate-spin" /> : <Lock size={16} />}
        {submitting ? t("buy.checkout.processing") : t("buy.checkout.pay")}
      </button>
      <p className="text-center font-mono text-[11px] text-depth/45" dir="ltr">
        {t("buy.checkout.currencyNote")}
      </p>
    </form>
  );
}
