import { motion } from "framer-motion";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";

// Tiny inline sparkline (no chart lib): animated line-draw + a live pulsing tip.
export function Sparkline({ data, color = "#28CFE0", width = 120, height = 36 }) {
  const reduced = usePrefersReducedMotion();
  if (!data || data.length < 2) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const stepX = width / (data.length - 1);
  const points = data.map((v, i) => {
    const x = i * stepX;
    const y = height - ((v - min) / span) * (height - 4) - 2;
    return [x, y];
  });
  const path = points.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area = `${path} L${width},${height} L0,${height} Z`;
  const gid = `spark-${color.replace("#", "")}`;
  const [ex, ey] = points[points.length - 1];
  // re-run the draw animation when the series changes
  const sig = `${data.length}:${data[data.length - 1]}`;

  return (
    <svg width={width} height={height} className="overflow-visible" aria-hidden="true">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.3" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <motion.path
        key={`a-${sig}`}
        d={area}
        fill={`url(#${gid})`}
        initial={reduced ? false : { opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.8, delay: 0.3 }}
      />
      <motion.path
        key={`l-${sig}`}
        d={path}
        fill="none"
        stroke={color}
        strokeWidth="1.9"
        strokeLinecap="round"
        strokeLinejoin="round"
        initial={reduced ? false : { pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 1, ease: [0.16, 1, 0.3, 1] }}
      />
      {/* live pulsing tip */}
      {!reduced && (
        <circle cx={ex} cy={ey} r="2.5" fill="none" stroke={color} strokeOpacity="0.6">
          <animate attributeName="r" values="2.5;7;2.5" dur="1.8s" repeatCount="indefinite" />
          <animate attributeName="stroke-opacity" values="0.6;0;0.6" dur="1.8s" repeatCount="indefinite" />
        </circle>
      )}
      <circle cx={ex} cy={ey} r="2.5" fill={color} />
    </svg>
  );
}
