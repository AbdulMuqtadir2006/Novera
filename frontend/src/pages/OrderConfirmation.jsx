import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { CheckCircle2, CircleAlert, Clock, Loader2, XCircle } from "lucide-react";
import { PageShell } from "../components/layout/PageShell";
import { getOrder } from "../lib/api";
import { useLang } from "../i18n/LanguageContext";

const STATUS_META = {
  pending: { icon: Clock, color: "text-status-watch" },
  paid: { icon: CheckCircle2, color: "text-status-good" },
  cancelled: { icon: XCircle, color: "text-depth/40" },
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
    <PageShell>
      <div className="mx-auto max-w-2xl">
        {error ? (
          <p className="text-center text-depth/60">{t("order.notFound")}</p>
        ) : !order ? (
          <div className="flex items-center justify-center gap-2 text-depth/50">
            <Loader2 size={18} className="animate-spin" /> {t("order.loading")}
          </div>
        ) : (
          <div className="light-card p-8">
            <div className="flex items-center gap-3">
              {StatusIcon && <StatusIcon size={28} className={meta.color} />}
              <div>
                <p className="eyebrow">{t("order.title")}</p>
                <h1 className="font-display text-2xl font-bold text-depth">{t(`order.status.${order.status}`)}</h1>
              </div>
            </div>

            <h2 className="mt-8 font-mono text-xs uppercase tracking-[0.16em] text-depth/45">
              {t("order.summary")}
            </h2>
            <ul className="mt-3 divide-y divide-depth/10">
              {order.items.map((item, i) => (
                <li key={i} className="flex items-center justify-between py-3">
                  <div>
                    <p className="text-sm font-medium text-depth">{item.name}</p>
                    <p className="text-xs text-depth/45">
                      {t(item.item_type === "device" ? "order.itemTypeDevice" : "order.itemTypeBundle")} · ×{item.quantity}
                    </p>
                  </div>
                  <span className="font-mono text-sm text-depth/70" dir="ltr">
                    ${item.line_total_usd.toFixed(2)}{" "}
                    <span className="text-xs text-depth/40">({item.line_total_omr.toFixed(3)} OMR)</span>
                  </span>
                </li>
              ))}
            </ul>

            <div className="mt-4 flex items-center justify-between border-t border-depth/10 pt-4">
              <span className="font-semibold text-depth">{t("order.total")}</span>
              <span className="font-display text-xl font-bold text-depth" dir="ltr">
                ${order.total_usd.toFixed(2)}{" "}
                <span className="font-mono text-xs font-normal text-depth/40">({order.total_omr.toFixed(3)} OMR)</span>
              </span>
            </div>

            <Link to="/buy" className="btn-ghost mt-8 inline-flex !border-depth/15 !text-depth">
              {t("order.backToBuy")}
            </Link>
          </div>
        )}
      </div>
    </PageShell>
  );
}
