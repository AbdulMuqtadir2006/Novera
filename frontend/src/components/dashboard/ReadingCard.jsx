import { motion } from "framer-motion";
import { StatusBadge } from "./StatusBadge";
import { Sparkline } from "./Sparkline";
import { AnimatedNumber } from "../ui/AnimatedNumber";
import { statusMeta, metricMeta } from "../../lib/format";
import { staggerItem } from "../ui/Reveal";
import { useLang } from "../../i18n/LanguageContext";

export function ReadingCard({ metricKey, metric, trend }) {
  const { t } = useLang();
  const meta = metricMeta[metricKey];
  const color = statusMeta[metric.status].color;

  return (
    <motion.div
      variants={staggerItem}
      whileHover={{ y: -4 }}
      transition={{ type: "spring", stiffness: 300, damping: 22 }}
      className="light-card group p-5 transition-shadow duration-300 hover:shadow-lift"
    >
      <div className="flex items-start justify-between">
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.14em] text-depth/50">
            {t(`metric.${metricKey}`)}
          </p>
          <div className="mt-2 flex items-baseline gap-1.5">
            <AnimatedNumber
              value={metric.value}
              decimals={meta.dp}
              duration={900}
              className="font-mono text-3xl font-semibold tabular-nums text-depth"
            />
            {metric.unit && (
              <span className="font-mono text-sm text-depth/50">{metric.unit}</span>
            )}
          </div>
        </div>
        <StatusBadge status={metric.status} />
      </div>

      <div className="mt-4">
        <Sparkline data={trend} color={color} width={180} height={40} />
      </div>

      <p className="mt-3 font-mono text-[11px] text-depth/40">
        {t("dash.reference")} {metric.range[0]}–{metric.range[1]}
        {metric.unit ? ` ${metric.unit}` : ""}
      </p>
    </motion.div>
  );
}
