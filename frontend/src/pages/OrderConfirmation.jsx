import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { motion } from "framer-motion";
import { CheckCircle2, CircleAlert, Clock, Loader2, XCircle } from "lucide-react";
import { getOrder } from "../lib/api";
import { useLang } from "../i18n/LanguageContext";

const STATUS_META = {
  pending: { icon: Clock, color: "text-status-watch" },
  paid: { icon: CheckCircle2, color: "text-status-good" },
  cancelled: { icon: XCircle, color: "text-slate-400" },
  failed: { icon: CircleAlert, color: "text-status-attention" },
};

// Shown after the Thawani redirect (backend's /api/orders/callback lands
// here). Always re-fetches the order's real status from the backend rather
// than trusting anything in the URL — the backend itself only marks an
// order paid after verifying with Thawani's own API (see
// routers/orders.py's thawani_callback()).
export default function OrderConfirmation() {
  const { token } = useParams();
  const { t } = useLang();
  const [order, setOrder] = useState(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    getOrder(token)
      .then(setOrder)
      .catch(() => setError(true));
  }, [token]);

  const meta = order ? STATUS_META[order.status] || STATUS_META.pending : null;
  const StatusIcon = meta?.icon;

  return (
    <motion.main
      className="relative min-h-screen bg-ink py-32"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.3 }}
    >
      <div className="container-page max-w-2xl">
        {error ? (
          <p className="text-center text-slate-300">{t("order.notFound")}</p>
        ) : !order ? (
          <div className="flex items-center justify-center gap-2 text-slate-400">
            <Loader2 size={18} className="animate-spin" /> {t("order.loading")}
          </div>
        ) : (
          <div className="glass-card p-8">
            <div className="flex items-center gap-3">
              {StatusIcon && <StatusIcon size={28} className={meta.color} />}
              <div>
                <p className="eyebrow">{t("order.title")}</p>
                <h1 className="font-display text-2xl font-bold text-white">{t(`order.status.${order.status}`)}</h1>
              </div>
            </div>

            <h2 className="mt-8 font-mono text-xs uppercase tracking-[0.16em] text-slate-500">
              {t("order.summary")}
            </h2>
            <ul className="mt-3 divide-y divide-white/10">
              {order.items.map((item, i) => (
                <li key={i} className="flex items-center justify-between py-3">
                  <div>
                    <p className="text-sm font-medium text-white">{item.name}</p>
                    <p className="text-xs text-slate-500">
                      {t(item.item_type === "device" ? "order.itemTypeDevice" : "order.itemTypeBundle")} · ×{item.quantity}
                    </p>
                  </div>
                  <span className="font-mono text-sm text-slate-300" dir="ltr">
                    {item.line_total_omr.toFixed(3)} OMR
                  </span>
                </li>
              ))}
            </ul>

            <div className="mt-4 flex items-center justify-between border-t border-white/10 pt-4">
              <span className="font-semibold text-white">{t("order.total")}</span>
              <span className="font-display text-xl font-bold text-white" dir="ltr">
                {order.total_omr.toFixed(3)} OMR
              </span>
            </div>

            <Link to="/buy" className="btn-ghost mt-8 inline-flex">
              {t("order.backToBuy")}
            </Link>
          </div>
        )}
      </div>
    </motion.main>
  );
}
