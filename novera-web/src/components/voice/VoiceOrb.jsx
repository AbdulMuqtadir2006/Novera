import { useMemo } from "react";
import { motion } from "framer-motion";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";

// interpolate cyan -> magenta -> purple around the ring
function barColor(tpos) {
  const stops = [
    [40, 207, 224],
    [236, 97, 232],
    [178, 75, 214],
    [40, 207, 224],
  ];
  const seg = tpos * (stops.length - 1);
  const i = Math.floor(seg);
  const f = seg - i;
  const a = stops[i];
  const b = stops[Math.min(i + 1, stops.length - 1)];
  const c = a.map((v, k) => Math.round(v + (b[k] - v) * f));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

const BAR_COUNT = 44;
const RADIUS = 118;

function Equalizer({ active }) {
  const bars = useMemo(
    () =>
      Array.from({ length: BAR_COUNT }, (_, i) => ({
        angle: (i / BAR_COUNT) * 360,
        color: barColor(i / BAR_COUNT),
        dur: 0.5 + Math.random() * 0.7,
        delay: Math.random() * 0.6,
        peak: 0.5 + Math.random() * 1.4,
      })),
    []
  );
  return (
    <div className="absolute inset-0">
      {bars.map((b, i) => (
        <motion.span
          key={i}
          className="absolute left-1/2 top-1/2 w-[3px] rounded-full"
          style={{
            height: 26,
            marginLeft: -1.5,
            background: `linear-gradient(to top, ${b.color}00, ${b.color})`,
            transform: `rotate(${b.angle}deg) translateY(-${RADIUS}px)`,
            transformOrigin: "center bottom",
          }}
          animate={
            active
              ? { scaleY: [0.28, b.peak, 0.5, b.peak * 0.7, 0.32], opacity: 0.95 }
              : { scaleY: 0.24, opacity: 0.4 }
          }
          transition={
            active
              ? { duration: b.dur, delay: b.delay, repeat: Infinity, ease: "easeInOut" }
              : { duration: 0.5 }
          }
        />
      ))}
    </div>
  );
}

// Interactive voice-agent orb. Rotating aurora blobs + a breathing gradient core
// + a circular equalizer that comes alive while `active` (speaking).
export function VoiceOrb({ active }) {
  const reduced = usePrefersReducedMotion();
  const live = active && !reduced;

  return (
    <div className="relative grid h-72 w-72 place-items-center">
      {/* rotating aurora — three blurred brand blobs */}
      {[
        { c: "bg-vital", x: -18, y: -14, dir: 1, base: 0.34 },
        { c: "bg-signal", x: 20, y: 10, dir: -1, base: 0.32 },
        { c: "bg-iris", x: -4, y: 20, dir: 1, base: 0.26 },
      ].map((b, i) => (
        <motion.div
          key={i}
          className={`absolute h-40 w-40 rounded-full ${b.c} blur-3xl`}
          style={{ x: b.x, y: b.y }}
          animate={
            reduced
              ? { opacity: b.base }
              : {
                  rotate: b.dir * 360,
                  scale: live ? [1, 1.22, 1] : [1, 1.06, 1],
                  opacity: live ? b.base + 0.22 : b.base,
                }
          }
          transition={{
            rotate: { duration: 14 + i * 5, repeat: Infinity, ease: "linear" },
            scale: { duration: live ? 1.6 : 5, repeat: Infinity, ease: "easeInOut" },
            opacity: { duration: 0.6 },
          }}
        />
      ))}

      {/* sonar rings while speaking */}
      {[0, 1, 2].map((r) => (
        <motion.span
          key={`ring-${r}`}
          className="absolute rounded-full border border-signal/40"
          style={{ width: 132, height: 132 }}
          animate={live ? { scale: [1, 2.0], opacity: [0.45, 0] } : { scale: 1, opacity: 0 }}
          transition={
            live
              ? { duration: 2.2, repeat: Infinity, delay: r * 0.7, ease: "easeOut" }
              : { duration: 0.4 }
          }
        />
      ))}

      <Equalizer active={live} />

      {/* core sphere */}
      <motion.div
        className="relative grid h-28 w-28 place-items-center rounded-full"
        style={{
          background:
            "radial-gradient(circle at 34% 28%, #7ef0ff, #28CFE0 34%, #B24BD6 72%, #EC61E8 100%)",
          boxShadow: "0 0 60px -6px rgba(40,207,224,0.55), inset 0 -10px 26px -8px rgba(11,8,25,0.55)",
        }}
        animate={
          reduced
            ? {}
            : live
            ? { scale: [1, 1.09, 0.97, 1.05, 1] }
            : { scale: [1, 1.05, 1] }
        }
        transition={{ duration: live ? 1.5 : 4.5, repeat: Infinity, ease: "easeInOut" }}
      >
        {/* inner waveform */}
        <div className="flex items-end gap-[3px]">
          {[0.55, 0.9, 0.68, 1, 0.72, 0.85].map((h, i) => (
            <motion.span
              key={i}
              className="w-[3px] rounded-full bg-white/90"
              style={{ height: 12 }}
              animate={live ? { height: [10, 10 + h * 30, 10] } : { height: 10 }}
              transition={
                live
                  ? { duration: 0.6 + i * 0.07, repeat: Infinity, ease: "easeInOut", delay: i * 0.04 }
                  : { duration: 0.3 }
              }
            />
          ))}
        </div>
      </motion.div>
    </div>
  );
}
